"""
The batch indent path must produce exactly what the per-item path produces.

``generate_batch`` loads a whole store's inputs in a fixed number of queries
instead of ~15 per item. That is only a safe optimisation if the two paths agree
on every field, for every shape of configuration — so this seeds a deliberately
awkward store (mixed forecast methods, per-item lookbacks, floors, MOQ, pack
sizes, surge, open indents, supplier lead times, missing data) and compares them
field by field.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.hospital import Hospital
from app.models.store import Store
from app.models.item import (
    ItemGroup, ItemCategory, Item, Supplier, ItemSupplier,
)
from app.models.settings import (
    HospitalSettings, StoreSettings, ItemSettings, ItemStoreSettings,
    ItemCategorySettings, ItemGroupSettings, SupplierSettings,
)
from app.models.consumption import ConsumptionRecord, ClosingStock, OpenIndent
from app.models.surge import SurgeRecord, get_season
from app.models.indent import TriggerType
from app.services.indent import (
    _build_indent_report, _load_store_batch, _build_from_batch, generate_batch,
)

AS_OF = date(2026, 4, 22)

# Every field the outbound pipeline and the UI read off a report.
COMPARED = [
    "item_id", "store_id", "period_start", "period_end",
    "avg_daily_consumption", "projected_need", "closing_stock_qty",
    "safety_stock_qty", "base_indent_qty", "surge_indent_qty",
    "open_indent_qty", "total_indent_qty", "formula_used", "request_type",
]


def _seed_awkward_store(db, forecast_method="baseline_avg"):
    """A store whose items exercise every branch of the calculation.

    ``forecast_method`` is a store-level setting (it is not resolvable per item),
    so the parity test parametrises over it rather than varying it item by item.
    """
    hospital = Hospital(name="H", code="H")
    db.add(hospital)
    db.flush()
    db.add(HospitalSettings(
        hospital_id=hospital.id, lookback_days=30, indent_duration_days=30,
        safety_stock_days=3.0, fsn_period_days=365, fsn_schedule_days=30,
        projection_formula="standard", forecast_method="baseline_avg",
        rolling_bucket_days=1, rolling_recent_weight_factor=2.0,
        trend_min_points=7,
    ))
    store = Store(hospital_id=hospital.id, name="S", code="S")
    db.add(store)
    db.flush()
    db.add(StoreSettings(
        store_id=store.id, lead_time_days=2,
        forecast_method=forecast_method,
        # bucket > 1 exercises the partial-bucket trim in the weighted path
        rolling_bucket_days=4, rolling_recent_weight_factor=3.0,
    ))

    group = ItemGroup(name="G")
    category = ItemCategory(name="C")
    db.add_all([group, category])
    db.flush()
    db.add(ItemGroupSettings(group_id=group.id, safety_stock_days=5.0))
    db.add(ItemCategorySettings(category_id=category.id, indent_duration_days=14))

    supplier = Supplier(name="Sup", code="SUP", lead_time_days=9)
    db.add(supplier)
    db.flush()
    db.add(SupplierSettings(supplier_id=supplier.id, lead_time_days=11))

    items = []
    for n in range(12):
        it = Item(
            name=f"Item{n}", code=f"I{n}", unit="Tabs",
            group_id=group.id if n % 2 else None,
            category_id=category.id if n % 3 else None,
        )
        db.add(it)
        items.append(it)
    db.flush()

    # --- consumption: different densities, gaps, and a duplicate-day row ---
    for n, it in enumerate(items):
        if n == 4:
            continue                      # no consumption at all
        for d in range(40):
            if n == 5 and d % 3:
                continue                  # sparse
            db.add(ConsumptionRecord(
                item_id=it.id, store_id=store.id,
                date=AS_OF - timedelta(days=40 - d),
                quantity=Decimal(str(5 + (n * d) % 7)),
            ))
    # two rows on the same day: baseline sums, dense series takes one
    db.add(ConsumptionRecord(
        item_id=items[6].id, store_id=store.id, date=AS_OF, quantity=Decimal("3"),
    ))

    # --- closing stock: varied, one item with none, one with two dates ---
    for n, it in enumerate(items):
        if n == 7:
            continue                      # no closing stock -> excluded from batch
        db.add(ClosingStock(
            item_id=it.id, store_id=store.id,
            date=AS_OF - timedelta(days=1), quantity=Decimal(str(20 + n)),
        ))
        if n == 8:
            db.add(ClosingStock(
                item_id=it.id, store_id=store.id,
                date=AS_OF, quantity=Decimal("999"),   # newer wins
            ))

    # --- open indents: latest snapshot only, summed across rows ---
    db.add(OpenIndent(item_id=items[1].id, store_id=store.id,
                      as_of_date=AS_OF - timedelta(days=5), quantity=Decimal("40")))
    db.add(OpenIndent(item_id=items[1].id, store_id=store.id,
                      as_of_date=AS_OF, quantity=Decimal("15")))
    db.add(OpenIndent(item_id=items[1].id, store_id=store.id,
                      as_of_date=AS_OF, quantity=Decimal("25")))   # summed with above
    db.add(OpenIndent(item_id=items[9].id, store_id=store.id,
                      as_of_date=AS_OF, quantity=Decimal("1000")))  # floors go negative

    # --- surge: month match, season match, and a disabled row ---
    target_month = (AS_OF + timedelta(days=1)).month
    target_season = get_season(target_month)

    def _surge(item, qty, enabled=True, month=None, season=None):
        return SurgeRecord(
            item_id=item.id, store_id=store.id, recorded_date=AS_OF,
            month=month if month is not None else target_month,
            season=season if season is not None else target_season,
            reason="test", extra_qty=Decimal(qty), enabled=enabled,
        )

    # two enabled rows -> averaged, not summed
    db.add(_surge(items[2], "12"))
    db.add(_surge(items[2], "18"))
    # disabled -> ignored entirely
    db.add(_surge(items[3], "50", enabled=False))
    # matches on season only (different month)
    db.add(_surge(items[11], "9", month=(target_month % 12) + 6))

    # --- per-item settings: forecast methods, lookbacks, floors, MOQ, packs ---
    # Deliberately mixed lookbacks: the batch path fetches one window sized to
    # the largest and slices each item's own out of it.
    db.add(ItemSettings(item_id=items[0].id, lookback_days=7))
    db.add(ItemSettings(item_id=items[1].id, lookback_days=13))
    db.add(ItemSettings(item_id=items[2].id, lookback_days=3))
    db.add(ItemSettings(item_id=items[3].id, lookback_days=35, pack_size=25))
    db.add(ItemSettings(item_id=items[5].id, lead_time_days=4))
    db.add(ItemSettings(item_id=items[10].id, planning_enabled=False))

    db.add(ItemStoreSettings(item_id=items[1].id, store_id=store.id, reorder_level=500.0))
    db.add(ItemStoreSettings(item_id=items[2].id, store_id=store.id, min_stock=800.0))
    db.add(ItemStoreSettings(item_id=items[3].id, store_id=store.id, min_order_qty=1000.0))
    db.add(ItemStoreSettings(item_id=items[5].id, store_id=store.id,
                             pack_size=7, safety_stock_days=1.5))
    db.add(ItemStoreSettings(item_id=items[9].id, store_id=store.id,
                             reorder_level=10.0, min_stock=5.0))

    # primary supplier for some items only
    db.add(ItemSupplier(item_id=items[6].id, supplier_id=supplier.id, is_primary=True))
    db.add(ItemSupplier(item_id=items[11].id, supplier_id=supplier.id, is_primary=True))

    db.commit()
    return store, items


def _fields(report):
    return {f: getattr(report, f) for f in COMPARED}


@pytest.mark.parametrize(
    "forecast_method", ["baseline_avg", "weighted_rolling", "trend_adjusted"]
)
def test_batch_matches_per_item_for_every_item(db, forecast_method):
    """Field-for-field equality between the two paths, for every forecast."""
    store, _items = _seed_awkward_store(db, forecast_method)

    item_ids = [
        r[0] for r in
        db.query(ClosingStock.item_id).filter(ClosingStock.store_id == store.id).distinct().all()
    ]
    assert len(item_ids) >= 10, "fixture should cover a meaningful number of items"

    batch = _load_store_batch(db, store.id, item_ids, AS_OF)

    compared = skipped = 0
    for iid in item_ids:
        try:
            expected = _fields(
                _build_indent_report(db, iid, store.id, AS_OF, TriggerType.scheduler)
            )
        except ValueError:
            # planning disabled — the batch path must refuse it too
            with pytest.raises(ValueError):
                _build_from_batch(batch, iid, TriggerType.scheduler)
            skipped += 1
            continue

        actual = _fields(_build_from_batch(batch, iid, TriggerType.scheduler))
        assert actual == expected, f"item {iid} diverged"
        compared += 1

    assert compared >= 9
    assert skipped == 1, "the planning-disabled item should have been refused by both"


def test_batch_query_count_is_flat_in_item_count(db):
    """The whole point: cost per store, not per item."""
    store, _items = _seed_awkward_store(db)
    item_ids = [
        r[0] for r in
        db.query(ClosingStock.item_id).filter(ClosingStock.store_id == store.id).distinct().all()
    ]

    from sqlalchemy import event
    n = [0]

    def _count(*a, **kw):
        n[0] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _count)
    try:
        n[0] = 0
        _load_store_batch(db, store.id, item_ids, AS_OF)
        batch_queries = n[0]

        n[0] = 0
        for iid in item_ids:
            try:
                _build_indent_report(db, iid, store.id, AS_OF, TriggerType.scheduler)
            except ValueError:
                pass
        per_item_queries = n[0]
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    # A fixed handful for the store, versus a multiple of the item count.
    assert batch_queries <= 20, f"batch path issued {batch_queries} queries"
    assert per_item_queries > 5 * len(item_ids)


def test_generate_batch_still_persists_and_dedupes(db):
    """End-to-end: the public entry point writes one report per item, and a
    second run replaces rather than duplicates them."""
    store, _items = _seed_awkward_store(db)

    reports, skipped = generate_batch(db, store.id, AS_OF, TriggerType.scheduler)
    assert len(reports) >= 9
    assert skipped == 1                      # the planning-disabled item

    from app.models.indent import IndentReport
    period_start = reports[0].period_start
    first = db.query(IndentReport).filter(
        IndentReport.store_id == store.id,
        IndentReport.period_start == period_start,
    ).count()
    assert first == len(reports)

    reports2, _ = generate_batch(db, store.id, AS_OF, TriggerType.scheduler)
    second = db.query(IndentReport).filter(
        IndentReport.store_id == store.id,
        IndentReport.period_start == period_start,
    ).count()
    assert second == first, "regeneration must replace, not duplicate"
    assert [float(r.total_indent_qty) for r in reports2] == \
           [float(r.total_indent_qty) for r in reports]


def test_generate_batch_preserves_pr_initiated_flag(db):
    """A raised Purchase Request must survive regeneration."""
    store, _items = _seed_awkward_store(db)
    from app.models.indent import IndentReport

    reports, _ = generate_batch(db, store.id, AS_OF, TriggerType.scheduler)
    target = reports[0].item_id
    db.query(IndentReport).filter(
        IndentReport.store_id == store.id, IndentReport.item_id == target
    ).update({"pr_initiated": True})
    db.commit()

    generate_batch(db, store.id, AS_OF, TriggerType.scheduler)
    still_set = db.query(IndentReport).filter(
        IndentReport.store_id == store.id,
        IndentReport.item_id == target,
        IndentReport.pr_initiated.is_(True),
    ).count()
    assert still_set == 1
