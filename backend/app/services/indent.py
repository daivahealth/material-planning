"""
Indent projection service.
Generates IndentReport records for (item, store) pairs.
"""
import logging
import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.consumption import ConsumptionRecord, ClosingStock, OpenIndent
from app.models.indent import IndentReport, TriggerType
from app.models.surge import SurgeRecord, get_season
from app.models.item import ItemSupplier, Supplier
from app.services import settings as settings_svc
from app.services.formula import (
    STANDARD_FORMULA,
    evaluate_formula,
)

log = logging.getLogger("indent")


def _get_lead_time_days(db: Session, item_id: int) -> int:
    """Return effective lead time (days) from the item's primary supplier.
    SupplierSettings.lead_time_days overrides Supplier.lead_time_days.
    Returns 0 when no primary supplier is set.
    """
    from app.models.settings import SupplierSettings
    row = (
        db.query(Supplier.lead_time_days, SupplierSettings.lead_time_days)
        .join(ItemSupplier, ItemSupplier.supplier_id == Supplier.id)
        .outerjoin(SupplierSettings, SupplierSettings.supplier_id == Supplier.id)
        .filter(ItemSupplier.item_id == item_id, ItemSupplier.is_primary.is_(True))
        .first()
    )
    if row is None:
        return 0
    base_lt, settings_lt = row
    return int(settings_lt) if settings_lt is not None else (int(base_lt) if base_lt else 0)


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
    avg = total / lookback_days if lookback_days > 0 else 0.0
    log.debug(
        "[item=%d store=%d] _avg_daily: lookback=%d days cutoff=%s total_qty=%.4f avg=%.4f",
        item_id, store_id, lookback_days, cutoff, total, avg,
    )
    return avg


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
    series: List[float] = []
    for i in range(lookback_days):
        day = start_day + timedelta(days=i)
        series.append(float(by_day.get(day, 0.0)))
    zero_days = sum(1 for v in series if v == 0.0)
    log.debug(
        "[item=%d store=%d] _daily_series: window=%d days (%s to %s) "
        "records_found=%d zero_days=%d non_zero_sum=%.4f",
        item_id, store_id, lookback_days, start_day, as_of,
        len(rows), zero_days, sum(v for v in series if v > 0),
    )
    return series


def _weighted_rolling_avg(db: Session, item_id: int, store_id: int,
                          window_days: int, bucket_days: int, recent_weight_factor: float,
                          as_of: date) -> float:
    """
    Weighted Consumption = ∑(Bucket Avg × Bucket Weight) / ∑Bucket Weights
    Each bucket covers `bucket_days` days; per-bucket value is avg daily consumption
    (same logic as _avg_daily).  Weights ramp linearly from 1.0 (oldest bucket) to
    `recent_weight_factor` (newest bucket).  When bucket_days=1 the behaviour is
    identical to the previous per-day implementation.
    """
    series = _daily_series(db, item_id, store_id, window_days, as_of)
    if not series:
        log.debug("[item=%d store=%d] _weighted_rolling_avg: empty series → 0.0", item_id, store_id)
        return 0.0

    n_full = len(series) // bucket_days
    if n_full < 1:
        # Not enough data for a single complete bucket — fall back to plain avg
        log.debug(
            "[item=%d store=%d] _weighted_rolling_avg: %d days < bucket_days %d → plain avg",
            item_id, store_id, len(series), bucket_days,
        )
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
    result = sum(v * w for v, w in zip(bucket_avgs, weights)) / denom
    log.debug(
        "[item=%d store=%d] _weighted_rolling_avg: window=%d bucket_days=%d "
        "n_buckets=%d weight_factor=%.2f result=%.4f",
        item_id, store_id, window_days, bucket_days, n, recent_weight_factor, result,
    )
    return result


def _trend_adjusted_avg(db: Session, item_id: int, store_id: int,
                        window_days: int, min_points: int,
                        as_of: date) -> float:
    series = _daily_series(db, item_id, store_id, window_days, as_of)
    n = len(series)
    if n < max(2, min_points):
        log.debug(
            "[item=%d store=%d] _trend_adjusted_avg: insufficient points (n=%d < min=%d) → fallback to simple avg",
            item_id, store_id, n, max(2, min_points),
        )
        return _avg_daily(db, item_id, store_id, window_days, as_of)

    x_mean = (n - 1) / 2.0
    y_mean = sum(series) / n
    sxx = sum((i - x_mean) ** 2 for i in range(n))
    if sxx == 0:
        log.debug(
            "[item=%d store=%d] _trend_adjusted_avg: zero variance (all values equal=%.4f)",
            item_id, store_id, y_mean,
        )
        return max(0.0, y_mean)
    sxy = sum((i - x_mean) * (series[i] - y_mean) for i in range(n))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean
    next_x = float(n)
    forecast = intercept + slope * next_x
    log.debug(
        "[item=%d store=%d] _trend_adjusted_avg: n=%d y_mean=%.4f slope=%.6f "
        "intercept=%.4f next_x=%.1f raw_forecast=%.4f clamped=%.4f",
        item_id, store_id, n, y_mean, slope, intercept, next_x, forecast, max(0.0, float(forecast)),
    )
    return max(0.0, float(forecast))


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
    qty = float(record.quantity) if record else 0.0
    log.debug(
        "[item=%d store=%d] _latest_closing_stock: record_date=%s qty=%.4f",
        item_id, store_id, record.date if record else None, qty,
    )
    return qty


def _open_indent_qty(db: Session, item_id: int, store_id: int, as_of: date) -> float:
    """Sum of open (pending) indent quantities for item/store as of the given date.
    Uses only the latest snapshot date to avoid accumulating historical imports.
    """
    latest_date = (
        db.query(func.max(OpenIndent.as_of_date))
        .filter(
            OpenIndent.item_id == item_id,
            OpenIndent.store_id == store_id,
            OpenIndent.as_of_date <= as_of,
        )
        .scalar()
    )
    if latest_date is None:
        log.debug("[item=%d store=%d] _open_indent_qty: no records → 0.0", item_id, store_id)
        return 0.0
    result = db.query(func.sum(OpenIndent.quantity)).filter(
        OpenIndent.item_id == item_id,
        OpenIndent.store_id == store_id,
        OpenIndent.as_of_date == latest_date,
    ).scalar()
    qty = float(result or 0)
    log.debug("[item=%d store=%d] _open_indent_qty: snapshot_date=%s qty=%.4f", item_id, store_id, latest_date, qty)
    return qty


def _surge_extra(db: Session, item_id: int, store_id: int, target_month: int) -> float:
    season = get_season(target_month)
    records = db.query(SurgeRecord).filter(
        SurgeRecord.item_id == item_id,
        SurgeRecord.store_id == store_id,
        (SurgeRecord.month == target_month) | (SurgeRecord.season == season),
    ).all()
    if not records:
        log.debug(
            "[item=%d store=%d] _surge_extra: month=%d season=%r → no surge records → 0.0",
            item_id, store_id, target_month, season,
        )
        return 0.0
    result = float(sum(r.extra_qty for r in records)) / len(records)
    log.debug(
        "[item=%d store=%d] _surge_extra: month=%d season=%r records=%d avg_extra=%.4f",
        item_id, store_id, target_month, season, len(records), result,
    )
    return result


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


def _build_indent_report(
    db: Session,
    item_id: int,
    store_id: int,
    as_of: date,
    triggered_by: TriggerType,
) -> IndentReport:
    """Calculate and construct an IndentReport without committing."""
    s = settings_svc.resolve_all(db, item_id, store_id)
    lookback_days: int = s["lookback_days"]
    indent_days: int = s["indent_duration_days"]
    safety_pct: float = s["safety_stock_pct"]
    formula_type: str = s["projection_formula"]
    formula_expr: Optional[str] = s["projection_formula_expr"]
    forecast_method: str = s["forecast_method"]
    rolling_bucket_days: int = s["rolling_bucket_days"]
    rolling_recent_weight_factor: float = s["rolling_recent_weight_factor"]
    trend_min_points: int = s["trend_min_points"]
    planning_enabled: bool = s["planning_enabled"]
    pack_size: int = int(s.get("pack_size") or 1)

    log.debug(
        "[item=%d store=%d] settings resolved: lookback=%d indent_days=%d "
        "safety_pct=%.4f forecast=%s formula=%s planning_enabled=%s",
        item_id, store_id, lookback_days, indent_days, safety_pct,
        forecast_method, formula_type, planning_enabled,
    )

    if not planning_enabled:
        log.info("[item=%d store=%d] planning_enabled=False → skipping", item_id, store_id)
        raise ValueError("Planning is disabled for this hospital/store/item combination")

    if forecast_method == "weighted_rolling":
        log.debug(
            "[item=%d store=%d] forecast: weighted_rolling lookback=%d bucket_days=%d weight_factor=%.2f",
            item_id, store_id, lookback_days, rolling_bucket_days, rolling_recent_weight_factor,
        )
        avg_daily = _weighted_rolling_avg(
            db, item_id, store_id, lookback_days,
            rolling_bucket_days, rolling_recent_weight_factor, as_of,
        )
    elif forecast_method == "trend_adjusted":
        log.debug(
            "[item=%d store=%d] forecast: trend_adjusted lookback=%d min_points=%d",
            item_id, store_id, lookback_days, trend_min_points,
        )
        avg_daily = _trend_adjusted_avg(
            db, item_id, store_id, lookback_days,
            trend_min_points, as_of,
        )
    else:
        log.debug(
            "[item=%d store=%d] forecast: baseline_avg lookback=%d",
            item_id, store_id, lookback_days,
        )
        avg_daily = _avg_daily(db, item_id, store_id, lookback_days, as_of)

    closing_stock = _latest_closing_stock(db, item_id, store_id, as_of)
    open_qty = _open_indent_qty(db, item_id, store_id, as_of)   # stock in transit

    # --- Target Stock Level ---
    # safety_stock_days converts the existing safety % into equivalent days of cover
    lead_time_days: int = _get_lead_time_days(db, item_id)
    safety_stock_days: float = safety_pct * indent_days
    target_stock_level: float = avg_daily * (indent_days + safety_stock_days + lead_time_days)
    safety_stock_qty: float = avg_daily * safety_stock_days

    log.debug(
        "[item=%d store=%d] intermediates: avg_daily=%.4f target_stock=%.4f "
        "closing=%.4f open=%.4f safety_days=%.2f lead_time=%d",
        item_id, store_id, avg_daily, target_stock_level, closing_stock, open_qty,
        safety_stock_days, lead_time_days,
    )

    if formula_type == "custom" and formula_expr:
        raw = evaluate_formula(
            formula_expr, avg_daily, indent_days, closing_stock, safety_pct, open_qty,
            lead_time_days=lead_time_days,
            safety_days=safety_stock_days,
            target_stock=target_stock_level,
        )
        base_indent = max(0.0, raw)
        formula_used = f"{forecast_method}:{formula_expr}"
        log.debug(
            "[item=%d store=%d] custom formula=%r raw=%.4f base_indent=%.4f",
            item_id, store_id, formula_expr, raw, base_indent,
        )
    else:
        # Reorder Quantity = Target Stock Level − (Stock On Hand + Stock In Transit)
        raw = target_stock_level - (closing_stock + open_qty)
        base_indent = max(0.0, raw)
        formula_used = f"{forecast_method}:{STANDARD_FORMULA}"
        log.debug(
            "[item=%d store=%d] standard formula: TSL=%.4f - (closing=%.4f + open=%.4f) = raw=%.4f base=%.4f",
            item_id, store_id, target_stock_level, closing_stock, open_qty, raw, base_indent,
        )

    target_month = (as_of + timedelta(days=1)).month  # indent is for NEXT period
    surge_qty = _surge_extra(db, item_id, store_id, target_month)
    total_indent = base_indent + surge_qty

    # Round up to the nearest pack multiple
    if pack_size > 1 and total_indent > 0:
        total_indent = math.ceil(total_indent / pack_size) * pack_size
        log.debug(
            "[item=%d store=%d] pack rounding: pack_size=%d → total_indent=%.4f",
            item_id, store_id, pack_size, total_indent,
        )

    log.info(
        "[item=%d store=%d] indent as_of=%s: avg_daily=%.4f target_stock=%.4f "
        "closing=%.4f open=%.4f safety_qty=%.4f surge=%.4f base=%.4f TOTAL=%.4f",
        item_id, store_id, as_of, avg_daily, target_stock_level,
        closing_stock, open_qty, safety_stock_qty, surge_qty, base_indent, total_indent,
    )

    period_start = as_of + timedelta(days=1)
    period_end = as_of + timedelta(days=indent_days)

    report = IndentReport(
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
    )
    return report


def generate_batch(
    db: Session,
    store_id: int,
    as_of: Optional[date] = None,
    triggered_by: TriggerType = TriggerType.api,
) -> tuple:
    """
    Generate indent reports for all items that have closing stock entries
    for the given store. Returns (reports, skipped_count).
    """
    # Only generate for items that have been tracked (have closing stock) at this store
    item_ids = [
        row[0] for row in
        db.query(ClosingStock.item_id)
        .filter(ClosingStock.store_id == store_id)
        .distinct()
        .all()
    ]
    if as_of is None:
        as_of = date.today()

    log.info(
        "[store=%d] generate_batch: as_of=%s triggered_by=%s items_to_process=%d",
        store_id, as_of, triggered_by.value, len(item_ids),
    )

    reports = []
    skipped = 0
    for item_id in item_ids:
        try:
            r = _build_indent_report(db, item_id, store_id, as_of, triggered_by)
            reports.append(r)
        except Exception as exc:
            log.warning(
                "[store=%d item=%d] generate_batch: skipped — %s",
                store_id, item_id, exc,
            )
            skipped += 1
    if reports:
        # Delete existing reports for this store/period before inserting to prevent duplicates
        period_start = reports[0].period_start
        item_ids_generated = [r.item_id for r in reports]
        db.query(IndentReport).filter(
            IndentReport.store_id == store_id,
            IndentReport.period_start == period_start,
            IndentReport.item_id.in_(item_ids_generated),
        ).delete(synchronize_session=False)
        db.add_all(reports)
        db.commit()

    log.info(
        "[store=%d] generate_batch done: generated=%d skipped=%d",
        store_id, len(reports), skipped,
    )
    return reports, skipped
