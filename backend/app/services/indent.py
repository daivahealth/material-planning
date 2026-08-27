"""
Indent projection service.
Generates IndentReport records for (item, store) pairs.

Two paths share one set of pure calculation cores, so they cannot drift:

  * ``generate_indent`` / ``_build_indent_report`` — single (item, store) pair.
    Fetches its own inputs; ~15 queries per pair.
  * ``generate_batch`` — every item of one store. Loads all inputs for the whole
    store in a fixed number of queries (~11) and then computes in Python.

The batch path exists because a network-wide run is 13k items x 200 stores =
2.6M pairs; at 15 queries each that is ~39M round trips, which saturates the
database for hours. Per store the batch path is ~11 queries regardless of item
count.
"""
import logging
import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.consumption import ConsumptionRecord, ClosingStock, OpenIndent
from app.models.indent import IndentReport, TriggerType
from app.models.surge import SurgeRecord, get_season
from app.models.item import Item, ItemSupplier, Supplier
from app.models.settings import (
    ItemSettings, StoreSettings, SupplierSettings, HospitalSettings,
    ItemCategorySettings, ItemGroupSettings, ItemStoreSettings,
)
from app.models.store import Store
from app.services import settings as settings_svc
from app.services.formula import (
    STANDARD_FORMULA,
    evaluate_formula,
)

log = logging.getLogger("indent")


# ═════════════════════════════════════════════════════════════════
# Pure calculation cores — no DB access.
# Both the single-pair and the batch path funnel through these.
# ═════════════════════════════════════════════════════════════════

def _series_from_daily(by_day: Dict[date, float], as_of: date,
                       lookback_days: int) -> List[float]:
    """Dense daily series over the LAST ``lookback_days`` days ending at as_of.

    Note this window is one day narrower than the baseline-average window
    below — that asymmetry is long-standing behaviour and is preserved here.
    """
    if lookback_days <= 0:
        return []
    start_day = as_of - timedelta(days=lookback_days - 1)
    return [
        float(by_day.get(start_day + timedelta(days=i), 0.0))
        for i in range(lookback_days)
    ]


def _weighted_from_series(series: List[float], bucket_days: int,
                          recent_weight_factor: float) -> float:
    """Weighted Consumption = sum(Bucket Avg x Weight) / sum(Weights).

    Weights ramp linearly from 1.0 (oldest bucket) to ``recent_weight_factor``
    (newest). With bucket_days=1 this is a per-day weighted average.
    """
    if not series:
        return 0.0
    n_full = len(series) // bucket_days
    if n_full < 1:
        # Not enough data for a single complete bucket — fall back to plain avg
        return sum(series) / len(series)

    # Drop oldest partial bucket so every bucket is complete
    trimmed = series[len(series) - n_full * bucket_days:]
    bucket_avgs = [
        sum(trimmed[i * bucket_days:(i + 1) * bucket_days]) / bucket_days
        for i in range(n_full)
    ]
    n = len(bucket_avgs)
    if n == 1:
        return bucket_avgs[0]

    step = (recent_weight_factor - 1.0) / (n - 1)
    weights = [1.0 + step * i for i in range(n)]
    denom = sum(weights)
    if denom <= 0:
        return 0.0
    return sum(v * w for v, w in zip(bucket_avgs, weights)) / denom


def _trend_from_series(series: List[float], min_points: int,
                       fallback_avg: float) -> float:
    """Least-squares trend extrapolated one step past the window.

    ``fallback_avg`` is used when there are too few points to fit — it must be
    the baseline average so the fallback matches the baseline_avg method.
    """
    n = len(series)
    if n < max(2, min_points):
        return fallback_avg

    x_mean = (n - 1) / 2.0
    y_mean = sum(series) / n
    sxx = sum((i - x_mean) ** 2 for i in range(n))
    if sxx == 0:
        return max(0.0, y_mean)
    sxy = sum((i - x_mean) * (series[i] - y_mean) for i in range(n))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean
    forecast = intercept + slope * float(n)
    return max(0.0, float(forecast))


def _forecast_avg_daily(
    *,
    method: str,
    lookback_days: int,
    bucket_days: int,
    weight_factor: float,
    trend_min_points: int,
    baseline_total: float,
    series: List[float],
) -> float:
    """Average daily demand from pre-fetched consumption.

    ``baseline_total`` is the summed quantity over [as_of - lookback, as_of]
    (inclusive both ends — one day wider than ``series``, matching the original
    per-pair SQL).
    """
    baseline = baseline_total / lookback_days if lookback_days > 0 else 0.0
    if method == "weighted_rolling":
        return _weighted_from_series(series, bucket_days, weight_factor)
    if method == "trend_adjusted":
        return _trend_from_series(series, trend_min_points, baseline)
    return baseline


def _lead_time_from(store_lt, item_lt, supplier_row) -> int:
    """Effective lead time (days) from already-resolved inputs.

    Priority: store override > item override > supplier settings > supplier
    default > 0. ``supplier_row`` is (supplier.lead_time_days,
    supplier_settings.lead_time_days) for the primary supplier, or None.
    """
    if store_lt is not None:
        return int(store_lt)
    if item_lt is not None:
        return int(item_lt)
    if supplier_row is None:
        return 0
    base_lt, settings_lt = supplier_row
    return int(settings_lt) if settings_lt is not None else (int(base_lt) if base_lt else 0)


def _surge_from_extras(extras: List[float]) -> float:
    """Average of the matching surge records' extra quantities (0 if none)."""
    if not extras:
        return 0.0
    return float(sum(extras)) / len(extras)


def _check_planning_enabled(s: dict, item_id: int, store_id: int) -> None:
    if not s["planning_enabled"]:
        log.debug("[item=%d store=%d] planning_enabled=False → skipping", item_id, store_id)
        raise ValueError("Planning is disabled for this hospital/store/item combination")


def _assemble_report(
    *,
    item_id: int,
    store_id: int,
    as_of: date,
    triggered_by: TriggerType,
    s: dict,
    avg_daily: float,
    closing_stock: float,
    open_qty: float,
    lead_time_days: int,
    surge_qty: float,
) -> IndentReport:
    """Turn resolved settings + fetched quantities into an IndentReport.

    Pure: every input is already resolved, so the single-pair and batch paths
    produce identical output by construction.
    """
    indent_days: int = s["indent_duration_days"]
    safety_stock_days: float = float(s["safety_stock_days"])
    formula_type: str = s["projection_formula"]
    formula_expr: Optional[str] = s["projection_formula_expr"]
    forecast_method: str = s["forecast_method"]
    pack_size: int = int(s.get("pack_size") or 1)
    request_type: Optional[str] = s.get("request_type")

    # --- Target Stock Level ---
    target_stock_level: float = avg_daily * (indent_days + safety_stock_days + lead_time_days)
    safety_stock_qty: float = avg_daily * safety_stock_days

    # safety_pct kept for backward-compat with custom formula expressions
    safety_pct: float = safety_stock_days / indent_days if indent_days > 0 else 0.0

    if formula_type == "custom" and formula_expr:
        raw = evaluate_formula(
            formula_expr, avg_daily, indent_days, closing_stock, safety_pct, open_qty,
            lead_time_days=lead_time_days,
            safety_days=safety_stock_days,
            target_stock=target_stock_level,
        )
        base_indent = max(0.0, raw)
        formula_used = f"{forecast_method}:{formula_expr}"
    else:
        # Reorder Quantity = Target Stock Level − (Stock On Hand + Stock In Transit)
        raw = target_stock_level - (closing_stock + open_qty)
        base_indent = max(0.0, raw)
        formula_used = f"{forecast_method}:{STANDARD_FORMULA}"

    # --- Reorder-point & minimum-stock floors ------------------------------
    # These raise the base indent so an item is replenished even when the
    # forecast alone would order little or nothing. Values are resolved through
    # the settings hierarchy (item×store > item > category > group > store >
    # hospital), so a value set at the item×store level takes effect here.
    #
    # Both floors work off the INVENTORY POSITION (stock on hand + stock already
    # on order), not bare closing stock — matching the standard formula above,
    # which subtracts open indents. Comparing against closing stock alone would
    # re-order quantities that are already in transit on every run until they
    # arrive.
    inventory_position = closing_stock + open_qty

    reorder_level = s.get("reorder_level")
    if reorder_level is not None and inventory_position < float(reorder_level):
        # Position has fallen below the reorder level → top up to that level.
        reorder_need = float(reorder_level) - inventory_position
        if reorder_need > base_indent:
            base_indent = reorder_need

    min_stock = s.get("min_stock")
    if min_stock is not None:
        # Bring the position up to the minimum level: order the shortfall
        # against on-hand + on-order — mirrors the reorder floor. Never lowers
        # an already-higher calculated base.
        min_need = float(min_stock) - inventory_position
        if min_need > base_indent:
            base_indent = min_need

    total_indent = base_indent + surge_qty

    # --- Minimum order quantity ------------------------------------------
    # Applies to the quantity actually being ordered (base + surge): if we are
    # ordering at all, order at least the MOQ.
    #
    # Deliberately NOT applied when the calculated quantity is zero — an item
    # that needs nothing must not be ordered just because an MOQ exists, which
    # would raise an order for every configured item every cycle.
    min_order_qty = s.get("min_order_qty")
    if min_order_qty is not None and total_indent > 0 and float(min_order_qty) > total_indent:
        total_indent = float(min_order_qty)

    # Round up to the nearest pack multiple
    if pack_size > 1 and total_indent > 0:
        total_indent = math.ceil(total_indent / pack_size) * pack_size

    # DEBUG, not INFO: at 2.6M pairs a per-item INFO line is 2.6M log lines per
    # network-wide run, which is real I/O contention on the way to the disk.
    log.debug(
        "[item=%d store=%d] indent as_of=%s: avg_daily=%.4f target_stock=%.4f "
        "closing=%.4f open=%.4f safety_qty=%.4f surge=%.4f base=%.4f TOTAL=%.4f",
        item_id, store_id, as_of, avg_daily, target_stock_level,
        closing_stock, open_qty, safety_stock_qty, surge_qty, base_indent, total_indent,
    )

    period_start = as_of + timedelta(days=1)
    period_end = as_of + timedelta(days=indent_days)

    return IndentReport(
        item_id=item_id,
        store_id=store_id,
        period_start=period_start,
        period_end=period_end,
        avg_daily_consumption=Decimal(str(round(avg_daily, 4))),
        projected_need=Decimal(str(round(target_stock_level, 4))),
        closing_stock_qty=Decimal(str(round(closing_stock, 4))),
        safety_stock_qty=Decimal(str(round(safety_stock_qty, 4))),
        base_indent_qty=Decimal(str(round(base_indent, 4))),
        surge_indent_qty=Decimal(str(round(surge_qty, 4))),
        open_indent_qty=Decimal(str(round(open_qty, 4))),
        total_indent_qty=Decimal(str(round(total_indent, 4))),
        formula_used=formula_used,
        triggered_by=triggered_by,
        request_type=request_type,
    )


# ═════════════════════════════════════════════════════════════════
# Single-pair DB helpers.
# Kept as the public surface used by the consumption-analysis API.
# ═════════════════════════════════════════════════════════════════

def _get_lead_time_days(db: Session, item_id: int, store_id: int) -> int:
    """Return effective lead time (days). See :func:`_lead_time_from`."""
    store_s = db.get(StoreSettings, store_id)
    item_s = db.get(ItemSettings, item_id)
    supplier_row = (
        db.query(Supplier.lead_time_days, SupplierSettings.lead_time_days)
        .join(ItemSupplier, ItemSupplier.supplier_id == Supplier.id)
        .outerjoin(SupplierSettings, SupplierSettings.supplier_id == Supplier.id)
        .filter(ItemSupplier.item_id == item_id, ItemSupplier.is_primary.is_(True))
        .first()
    )
    return _lead_time_from(
        _get_attr(store_s, "lead_time_days"),
        _get_attr(item_s, "lead_time_days"),
        supplier_row,
    )


def _get_attr(obj, name):
    return getattr(obj, name, None) if obj is not None else None


def _avg_daily(db: Session, item_id: int, store_id: int,
               lookback_days: int, as_of: date) -> float:
    cutoff = as_of - timedelta(days=lookback_days)
    result = db.query(func.sum(ConsumptionRecord.quantity)).filter(
        ConsumptionRecord.item_id == item_id,
        ConsumptionRecord.store_id == store_id,
        ConsumptionRecord.date >= cutoff,
        ConsumptionRecord.date <= as_of,
    ).scalar()
    total = float(result or 0)
    return total / lookback_days if lookback_days > 0 else 0.0


def _daily_series(db: Session, item_id: int, store_id: int,
                  lookback_days: int, as_of: date) -> List[float]:
    if lookback_days <= 0:
        return []
    start_day = as_of - timedelta(days=lookback_days - 1)
    rows = db.query(ConsumptionRecord.date, ConsumptionRecord.quantity).filter(
        ConsumptionRecord.item_id == item_id,
        ConsumptionRecord.store_id == store_id,
        ConsumptionRecord.date >= start_day,
        ConsumptionRecord.date <= as_of,
    ).all()
    by_day = {d: float(q) for d, q in rows}
    return _series_from_daily(by_day, as_of, lookback_days)


def _weighted_rolling_avg(db: Session, item_id: int, store_id: int,
                          window_days: int, bucket_days: int, recent_weight_factor: float,
                          as_of: date) -> float:
    series = _daily_series(db, item_id, store_id, window_days, as_of)
    return _weighted_from_series(series, bucket_days, recent_weight_factor)


def _trend_adjusted_avg(db: Session, item_id: int, store_id: int,
                        window_days: int, min_points: int,
                        as_of: date) -> float:
    series = _daily_series(db, item_id, store_id, window_days, as_of)
    if len(series) < max(2, min_points):
        # Fetch the baseline only when it is actually needed as the fallback.
        return _avg_daily(db, item_id, store_id, window_days, as_of)
    return _trend_from_series(series, min_points, 0.0)


def _latest_closing_stock(db: Session, item_id: int, store_id: int,
                          as_of: date) -> float:
    record = (
        db.query(ClosingStock)
        .filter(
            ClosingStock.item_id == item_id,
            ClosingStock.store_id == store_id,
            ClosingStock.date <= as_of,
        )
        .order_by(ClosingStock.date.desc())
        .first()
    )
    return float(record.quantity) if record else 0.0


def _open_indent_qty(db: Session, item_id: int, store_id: int, as_of: date) -> float:
    """Open (pending) indent quantity for item/store STRICTLY as on ``as_of``.

    Only rows dated exactly ``as_of`` count; multiple rows on that date are
    summed. An item absent from the ``as_of`` snapshot has **no** open indent —
    it is not carried forward from an earlier date.

    This matters because the feed is an authoritative daily snapshot: an item
    whose indent has been received simply stops appearing. Falling back to the
    last date it *did* appear would subtract a phantom quantity from the
    inventory position forever, permanently under-ordering that item.
    """
    result = db.query(func.sum(OpenIndent.quantity)).filter(
        OpenIndent.item_id == item_id,
        OpenIndent.store_id == store_id,
        OpenIndent.as_of_date == as_of,
    ).scalar()
    return float(result or 0)


def _surge_extra(db: Session, item_id: int, store_id: int, target_month: int) -> float:
    season = get_season(target_month)
    records = db.query(SurgeRecord.extra_qty).filter(
        SurgeRecord.item_id == item_id,
        SurgeRecord.store_id == store_id,
        SurgeRecord.enabled.is_(True),
        (SurgeRecord.month == target_month) | (SurgeRecord.season == season),
    ).all()
    return _surge_from_extras([r[0] for r in records])


def _build_indent_report(
    db: Session,
    item_id: int,
    store_id: int,
    as_of: date,
    triggered_by: TriggerType,
) -> IndentReport:
    """Calculate and construct an IndentReport for one pair, without committing."""
    s = settings_svc.resolve_all(db, item_id, store_id)
    _check_planning_enabled(s, item_id, store_id)

    lookback_days: int = s["lookback_days"]
    forecast_method: str = s["forecast_method"]

    if forecast_method == "weighted_rolling":
        avg_daily = _weighted_rolling_avg(
            db, item_id, store_id, lookback_days,
            s["rolling_bucket_days"], s["rolling_recent_weight_factor"], as_of,
        )
    elif forecast_method == "trend_adjusted":
        avg_daily = _trend_adjusted_avg(
            db, item_id, store_id, lookback_days, s["trend_min_points"], as_of,
        )
    else:
        avg_daily = _avg_daily(db, item_id, store_id, lookback_days, as_of)

    target_month = (as_of + timedelta(days=1)).month  # indent is for NEXT period
    return _assemble_report(
        item_id=item_id,
        store_id=store_id,
        as_of=as_of,
        triggered_by=triggered_by,
        s=s,
        avg_daily=avg_daily,
        closing_stock=_latest_closing_stock(db, item_id, store_id, as_of),
        open_qty=_open_indent_qty(db, item_id, store_id, as_of),
        lead_time_days=_get_lead_time_days(db, item_id, store_id),
        surge_qty=_surge_extra(db, item_id, store_id, target_month),
    )


def generate_indent(
    db: Session,
    item_id: int,
    store_id: int,
    as_of: Optional[date] = None,
    triggered_by: TriggerType = TriggerType.api,
) -> IndentReport:
    if as_of is None:
        as_of = date.today()

    report = _build_indent_report(db, item_id, store_id, as_of, triggered_by)
    # Replace any existing report for the same item/store/period to prevent duplicates
    db.query(IndentReport).filter(
        IndentReport.item_id == item_id,
        IndentReport.store_id == store_id,
        IndentReport.period_start == report.period_start,
    ).delete(synchronize_session=False)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


# ═════════════════════════════════════════════════════════════════
# Batch path — one store, every item, fixed query count
# ═════════════════════════════════════════════════════════════════

class _StoreBatch:
    """All inputs needed to compute every item's indent for one store.

    Loaded in ~11 queries total rather than ~15 per item. Every lookup below is
    an in-memory dict; nothing here touches the database.
    """

    __slots__ = (
        "store_id", "as_of", "settings", "closing", "open_qty",
        "consumption", "surge", "lead_time",
    )

    def __init__(self, store_id: int, as_of: date):
        self.store_id = store_id
        self.as_of = as_of
        self.settings: Dict[int, dict] = {}
        self.closing: Dict[int, float] = {}
        self.open_qty: Dict[int, float] = {}
        self.consumption: Dict[int, List[Tuple[date, float]]] = {}
        self.surge: Dict[int, List[float]] = {}
        self.lead_time: Dict[int, int] = {}


class ItemLevelCache:
    """Item-scoped settings tables, reusable across stores within one run.

    Nothing here depends on the store, so a network-wide run that builds one of
    these up front loads them once instead of once per store (200 stores x ~13k
    items is otherwise millions of rows and ORM instances rebuilt for nothing).

    The trade-off is that a run sees the item settings as they were when it
    started. For a job that regenerates the whole network that is the desirable
    behaviour anyway — every store is planned against the same configuration.
    """

    __slots__ = ("items", "item_settings", "cat_settings", "grp_settings")

    def __init__(self, db: Session):
        self.items = {
            i.id: i for i in
            db.query(Item.id, Item.category_id, Item.group_id).all()
        }
        self.item_settings = {r.item_id: r for r in db.query(ItemSettings).all()}
        self.cat_settings = {r.category_id: r for r in db.query(ItemCategorySettings).all()}
        self.grp_settings = {r.group_id: r for r in db.query(ItemGroupSettings).all()}


def _load_store_batch(db: Session, store_id: int, item_ids: List[int],
                      as_of: date,
                      item_cache: Optional[ItemLevelCache] = None) -> _StoreBatch:
    """Load every input for a store's items.

    Filters are store-wide rather than ``item_id IN (13k ids)`` — a huge IN list
    costs more to parse than the scan it saves, and the tables are already
    narrowed hard by store_id.

    ``item_cache`` lets a multi-store run share the item-scoped tables; when it
    is None they are loaded for this store alone.
    """
    batch = _StoreBatch(store_id, as_of)
    if not item_ids:
        return batch
    wanted = set(item_ids)

    # --- 1-3. store-level rows (one row each) ---
    store_s = db.get(StoreSettings, store_id)
    store = db.get(Store, store_id)
    hospital_s = db.get(HospitalSettings, store.hospital_id) if store else None

    # --- 4-8. settings hierarchy, whole-table loads (bounded by item count) ---
    cache = item_cache if item_cache is not None else ItemLevelCache(db)
    items = cache.items
    item_settings = cache.item_settings
    cat_settings = cache.cat_settings
    grp_settings = cache.grp_settings
    item_store_settings = {
        r.item_id: r for r in
        db.query(ItemStoreSettings).filter(ItemStoreSettings.store_id == store_id).all()
    }

    for iid in wanted:
        item = items.get(iid)
        batch.settings[iid] = settings_svc.resolve_from_sources(
            item_store_s=item_store_settings.get(iid),
            item_s=item_settings.get(iid),
            cat_s=cat_settings.get(item.category_id) if item and item.category_id else None,
            grp_s=grp_settings.get(item.group_id) if item and item.group_id else None,
            store_s=store_s,
            hospital_s=hospital_s,
        )

    # --- 9. consumption over the widest lookback any item asks for ---
    # Each item slices its own window out of this; fetching per item is what
    # made the old path N+1.
    max_lookback = max(
        (int(s["lookback_days"]) for s in batch.settings.values()), default=0
    )
    if max_lookback > 0:
        window_start = as_of - timedelta(days=max_lookback)
        for iid, d, q in db.query(
            ConsumptionRecord.item_id, ConsumptionRecord.date, ConsumptionRecord.quantity
        ).filter(
            ConsumptionRecord.store_id == store_id,
            ConsumptionRecord.date >= window_start,
            ConsumptionRecord.date <= as_of,
        ).all():
            if iid in wanted:
                batch.consumption.setdefault(iid, []).append((d, float(q)))

    # --- 10. latest closing stock per item (mirrors _latest_closing_stock) ---
    latest_cs = (
        db.query(
            ClosingStock.item_id.label("item_id"),
            func.max(ClosingStock.date).label("d"),
        )
        .filter(ClosingStock.store_id == store_id, ClosingStock.date <= as_of)
        .group_by(ClosingStock.item_id)
        .subquery()
    )
    for iid, qty in (
        db.query(ClosingStock.item_id, ClosingStock.quantity)
        .join(latest_cs, and_(latest_cs.c.item_id == ClosingStock.item_id,
                              latest_cs.c.d == ClosingStock.date))
        .filter(ClosingStock.store_id == store_id)
        .all()
    ):
        # Duplicate rows on the same date: first wins, as .first() did before.
        if iid in wanted and iid not in batch.closing:
            batch.closing[iid] = float(qty)

    # --- 11. open indents strictly as on as_of (mirrors _open_indent_qty) ---
    # No latest-date fallback: an item missing from the as_of snapshot has no
    # open indent. See _open_indent_qty for why carrying forward is wrong.
    for iid, qty in (
        db.query(OpenIndent.item_id, func.sum(OpenIndent.quantity))
        .filter(OpenIndent.store_id == store_id, OpenIndent.as_of_date == as_of)
        .group_by(OpenIndent.item_id)
        .all()
    ):
        if iid in wanted:
            batch.open_qty[iid] = float(qty or 0)

    # --- 12. surge records matching the target month/season ---
    target_month = (as_of + timedelta(days=1)).month
    season = get_season(target_month)
    for iid, extra in (
        db.query(SurgeRecord.item_id, SurgeRecord.extra_qty)
        .filter(
            SurgeRecord.store_id == store_id,
            SurgeRecord.enabled.is_(True),
            (SurgeRecord.month == target_month) | (SurgeRecord.season == season),
        )
        .all()
    ):
        if iid in wanted:
            batch.surge.setdefault(iid, []).append(extra)

    # --- 13. primary-supplier lead times ---
    supplier_rows: Dict[int, tuple] = {}
    for iid, base_lt, settings_lt in (
        db.query(ItemSupplier.item_id, Supplier.lead_time_days, SupplierSettings.lead_time_days)
        .join(Supplier, ItemSupplier.supplier_id == Supplier.id)
        .outerjoin(SupplierSettings, SupplierSettings.supplier_id == Supplier.id)
        .filter(ItemSupplier.is_primary.is_(True))
        .all()
    ):
        # First row per item wins, as .first() did before.
        if iid in wanted and iid not in supplier_rows:
            supplier_rows[iid] = (base_lt, settings_lt)

    store_lt = _get_attr(store_s, "lead_time_days")
    for iid in wanted:
        batch.lead_time[iid] = _lead_time_from(
            store_lt,
            _get_attr(item_settings.get(iid), "lead_time_days"),
            supplier_rows.get(iid),
        )

    return batch


def _build_from_batch(batch: _StoreBatch, item_id: int,
                      triggered_by: TriggerType) -> IndentReport:
    """Compute one item's report from pre-loaded batch inputs. No DB access."""
    s = batch.settings[item_id]
    _check_planning_enabled(s, item_id, batch.store_id)

    as_of = batch.as_of
    lookback_days: int = s["lookback_days"]

    # The baseline window sums duplicates while the dense series is last-wins —
    # both reproduce the original per-pair queries exactly.
    rows = batch.consumption.get(item_id, ())
    cutoff = as_of - timedelta(days=lookback_days)
    baseline_total = sum(q for d, q in rows if cutoff <= d <= as_of)
    by_day = {d: q for d, q in rows}

    avg_daily = _forecast_avg_daily(
        method=s["forecast_method"],
        lookback_days=lookback_days,
        bucket_days=s["rolling_bucket_days"],
        weight_factor=s["rolling_recent_weight_factor"],
        trend_min_points=s["trend_min_points"],
        baseline_total=baseline_total,
        series=_series_from_daily(by_day, as_of, lookback_days),
    )

    return _assemble_report(
        item_id=item_id,
        store_id=batch.store_id,
        as_of=as_of,
        triggered_by=triggered_by,
        s=s,
        avg_daily=avg_daily,
        closing_stock=batch.closing.get(item_id, 0.0),
        open_qty=batch.open_qty.get(item_id, 0.0),
        lead_time_days=batch.lead_time.get(item_id, 0),
        surge_qty=_surge_from_extras(batch.surge.get(item_id, [])),
    )


def generate_batch(
    db: Session,
    store_id: int,
    as_of: Optional[date] = None,
    triggered_by: TriggerType = TriggerType.api,
    item_cache: Optional[ItemLevelCache] = None,
) -> tuple:
    """
    Generate indent reports for all items that have closing stock entries
    for the given store. Returns (reports, skipped_count).

    ``item_cache`` is an optimisation for callers that loop over many stores
    (see :class:`ItemLevelCache`); omit it for a one-off store.
    """
    if as_of is None:
        as_of = date.today()

    # Only generate for items that have been tracked (have closing stock) at this store
    item_ids = [
        row[0] for row in
        db.query(ClosingStock.item_id)
        .filter(ClosingStock.store_id == store_id)
        .distinct()
        .all()
    ]

    log.info(
        "[store=%d] generate_batch: as_of=%s triggered_by=%s items_to_process=%d",
        store_id, as_of, triggered_by.value, len(item_ids),
    )

    batch = _load_store_batch(db, store_id, item_ids, as_of, item_cache)

    reports = []
    skipped = 0
    for item_id in item_ids:
        try:
            reports.append(_build_from_batch(batch, item_id, triggered_by))
        except Exception as exc:
            log.debug(
                "[store=%d item=%d] generate_batch: skipped — %s",
                store_id, item_id, exc,
            )
            skipped += 1
    if reports:
        # Delete existing reports for this store/period before inserting to prevent duplicates
        period_start = reports[0].period_start
        item_ids_generated = [r.item_id for r in reports]
        # Preserve the pr_initiated flag across regeneration so a raised Purchase
        # Request is not silently reset and re-offered for PR creation.
        pr_done = {
            row[0] for row in
            db.query(IndentReport.item_id).filter(
                IndentReport.store_id == store_id,
                IndentReport.period_start == period_start,
                IndentReport.item_id.in_(item_ids_generated),
                IndentReport.pr_initiated.is_(True),
            ).all()
        }
        if pr_done:
            for r in reports:
                if r.item_id in pr_done:
                    r.pr_initiated = True
        db.query(IndentReport).filter(
            IndentReport.store_id == store_id,
            IndentReport.period_start == period_start,
            IndentReport.item_id.in_(item_ids_generated),
        ).delete(synchronize_session=False)
        db.add_all(reports)
        db.commit()
        # Detach the persisted reports. A network-wide run calls this once per
        # store, so without this the session's identity map grows by every
        # report ever written (13k x 200 stores) and each flush has to walk it.
        # Safe only when the session does not expire on commit: the caller still
        # reads item_id/total_indent_qty off these instances, and a detached
        # instance can only serve values that were not expired out from under it.
        if not db.expire_on_commit:
            for r in reports:
                db.expunge(r)

    log.info(
        "[store=%d] generate_batch done: generated=%d skipped=%d",
        store_id, len(reports), skipped,
    )
    return reports, skipped
