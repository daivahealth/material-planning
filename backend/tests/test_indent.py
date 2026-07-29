"""
Tests for IndentProjectionService.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.models.hospital import Hospital
from app.models.store import Store
from app.models.item import ItemGroup, ItemCategory, Item
from app.models.settings import HospitalSettings
from app.models.consumption import ConsumptionRecord, ClosingStock
from app.models.surge import SurgeRecord, SeasonType
from app.services.indent import generate_indent


def _seed(db):
    hospital = Hospital(name="H", code="H")
    db.add(hospital)
    db.flush()
    db.add(HospitalSettings(
        hospital_id=hospital.id, lookback_days=30, indent_duration_days=30,
        safety_stock_days=3.0, fsn_period_days=365, fsn_schedule_days=30,
        projection_formula="standard",
    ))
    store = Store(hospital_id=hospital.id, name="S", code="S")
    db.add(store)
    db.flush()
    item = Item(name="Drug", code="DRG", unit="Tabs")
    db.add(item)
    db.flush()
    return store, item


def test_standard_formula_correct(db):
    store, item = _seed(db)
    today = date(2026, 4, 22)
    # 30 days of consumption: 10/day
    for d in range(30):
        db.add(ConsumptionRecord(
            item_id=item.id, store_id=store.id,
            date=today - timedelta(days=30 - d),
            quantity=Decimal("10"),
        ))
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("50")))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    # avg_daily=10, TSL=10*(30+3+0)=330, safety=10*3=30, base=330-50=280
    assert float(report.avg_daily_consumption) == pytest.approx(10.0, abs=0.01)
    assert float(report.projected_need) == pytest.approx(330.0, abs=0.01)
    assert float(report.safety_stock_qty) == pytest.approx(30.0, abs=0.01)
    assert float(report.base_indent_qty) == pytest.approx(280.0, abs=0.01)
    assert float(report.surge_indent_qty) == 0.0
    assert float(report.total_indent_qty) == pytest.approx(280.0, abs=0.01)


def test_base_indent_never_negative(db):
    store, item = _seed(db)
    today = date(2026, 4, 22)
    for d in range(30):
        db.add(ConsumptionRecord(
            item_id=item.id, store_id=store.id,
            date=today - timedelta(days=30 - d),
            quantity=Decimal("5"),
        ))
    # Very large closing stock → base indent should be 0
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("9999")))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    assert float(report.base_indent_qty) == 0.0


def test_surge_added_to_total(db):
    store, item = _seed(db)
    today = date(2026, 4, 22)  # April → month 4 → Summer
    for d in range(30):
        db.add(ConsumptionRecord(
            item_id=item.id, store_id=store.id,
            date=today - timedelta(days=30 - d),
            quantity=Decimal("10"),
        ))
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("50")))
    # Surge recorded in previous Summer (same season as next period)
    db.add(SurgeRecord(
        item_id=item.id, store_id=store.id,
        recorded_date=date(2025, 4, 10), month=4,
        season=SeasonType.Summer, reason="Test surge", extra_qty=Decimal("100"),
    ))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    assert float(report.surge_indent_qty) == pytest.approx(100.0, abs=0.01)
    assert float(report.total_indent_qty) == pytest.approx(380.0, abs=0.01)


def test_zero_consumption_gives_zero_base(db):
    store, item = _seed(db)
    today = date(2026, 4, 22)
    # No consumption records at all
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("100")))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    assert float(report.avg_daily_consumption) == 0.0
    assert float(report.base_indent_qty) == 0.0


def test_custom_formula_used(db):
    store, item = _seed(db)
    # Switch hospital to custom formula
    from app.models.settings import HospitalSettings
    hs = db.query(HospitalSettings).first()
    hs.projection_formula = "custom"
    hs.projection_formula_expr = "avg_daily * indent_days * 2"
    db.flush()

    today = date(2026, 4, 22)
    for d in range(30):
        db.add(ConsumptionRecord(
            item_id=item.id, store_id=store.id,
            date=today - timedelta(days=30 - d),
            quantity=Decimal("10"),
        ))
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("0")))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    # custom: 10 * 30 * 2 = 600
    assert float(report.base_indent_qty) == pytest.approx(600.0, abs=0.01)
    assert "avg_daily * indent_days * 2" in report.formula_used


def test_weighted_rolling_method_changes_avg_daily(db):
    store, item = _seed(db)
    hs = db.query(HospitalSettings).first()
    hs.forecast_method = "weighted_rolling"
    hs.lookback_days = 5
    hs.rolling_recent_weight_factor = 3.0
    db.flush()

    today = date(2026, 4, 22)
    # Increasing recent usage: [1,2,3,4,5]
    for i, q in enumerate([1, 2, 3, 4, 5]):
        db.add(ConsumptionRecord(
            item_id=item.id,
            store_id=store.id,
            date=today - timedelta(days=4 - i),
            quantity=Decimal(str(q)),
        ))
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("0")))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    # Weighted average should be above simple mean (3.0) for increasing sequence.
    assert float(report.avg_daily_consumption) > 3.0
    assert "weighted_rolling" in report.formula_used


def test_trend_adjusted_method_projects_upward(db):
    store, item = _seed(db)
    hs = db.query(HospitalSettings).first()
    hs.forecast_method = "trend_adjusted"
    hs.lookback_days = 7
    hs.trend_min_points = 7
    db.flush()

    today = date(2026, 4, 22)
    # Clear upward trend: 2,4,6,8,10,12,14
    seq = [2, 4, 6, 8, 10, 12, 14]
    for i, q in enumerate(seq):
        db.add(ConsumptionRecord(
            item_id=item.id,
            store_id=store.id,
            date=today - timedelta(days=6 - i),
            quantity=Decimal(str(q)),
        ))
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("0")))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    # Trend-adjusted next-point forecast should exceed plain average (8.0).
    assert float(report.avg_daily_consumption) > 8.0
    assert "trend_adjusted" in report.formula_used


def test_planning_disabled_blocks_indent_generation(db):
    store, item = _seed(db)
    hs = db.query(HospitalSettings).first()
    hs.planning_enabled = False
    db.flush()

    with pytest.raises(ValueError, match="Planning is disabled"):
        generate_indent(db, item.id, store.id, date(2026, 4, 22))


def test_weighted_rolling_bucket_grouping(db):
    """Bucket-level weighting: 3 weekly buckets (2/day, 5/day, 8/day).
    With recent_weight_factor=3, weighted avg should exceed the simple mean (5.0).
    """
    store, item = _seed(db)
    hs = db.query(HospitalSettings).first()
    hs.forecast_method = "weighted_rolling"
    hs.lookback_days = 21
    hs.rolling_bucket_days = 7
    hs.rolling_recent_weight_factor = 3.0
    db.flush()

    today = date(2026, 4, 22)
    # week 1 (oldest): 2/day, week 2: 5/day, week 3 (newest): 8/day
    for week, qty in enumerate([2, 5, 8]):
        for day in range(7):
            db.add(ConsumptionRecord(
                item_id=item.id, store_id=store.id,
                date=today - timedelta(days=20 - (week * 7 + day)),
                quantity=Decimal(str(qty)),
            ))
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("0")))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    # Simple mean of bucket avgs = (2+5+8)/3 = 5.0; weighted result must exceed that
    assert float(report.avg_daily_consumption) > 5.0
    assert "weighted_rolling" in report.formula_used


def test_min_order_qty_raises_total(db):
    """MOQ at item x store lifts an otherwise-smaller order up to the minimum."""
    from app.models.settings import ItemStoreSettings

    store, item = _seed(db)
    today = date(2026, 4, 22)
    for d in range(30):
        db.add(ConsumptionRecord(
            item_id=item.id, store_id=store.id,
            date=today - timedelta(days=30 - d), quantity=Decimal("10"),
        ))
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("50")))
    db.add(ItemStoreSettings(item_id=item.id, store_id=store.id, min_order_qty=500))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    # Calculated total would be 280 (see test_standard_formula_correct); MOQ wins.
    assert float(report.base_indent_qty) == pytest.approx(280.0, abs=0.01)
    assert float(report.total_indent_qty) == pytest.approx(500.0, abs=0.01)


def test_min_order_qty_does_not_lower_a_larger_order(db):
    """MOQ is a floor, never a cap."""
    from app.models.settings import ItemStoreSettings

    store, item = _seed(db)
    today = date(2026, 4, 22)
    for d in range(30):
        db.add(ConsumptionRecord(
            item_id=item.id, store_id=store.id,
            date=today - timedelta(days=30 - d), quantity=Decimal("10"),
        ))
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("50")))
    db.add(ItemStoreSettings(item_id=item.id, store_id=store.id, min_order_qty=100))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    assert float(report.total_indent_qty) == pytest.approx(280.0, abs=0.01)


def test_min_order_qty_not_applied_when_nothing_is_needed(db):
    """An item needing nothing must not be ordered just because an MOQ exists."""
    from app.models.settings import ItemStoreSettings

    store, item = _seed(db)
    today = date(2026, 4, 22)
    # No consumption + plenty of stock → calculated requirement is zero.
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("9999")))
    db.add(ItemStoreSettings(item_id=item.id, store_id=store.id, min_order_qty=500))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    assert float(report.total_indent_qty) == 0.0


def test_reorder_floor_accounts_for_open_indents(db):
    """Stock already on order must not be re-ordered by the reorder floor."""
    from app.models.settings import ItemStoreSettings
    from app.models.consumption import OpenIndent

    store, item = _seed(db)
    today = date(2026, 4, 22)
    # No consumption → the forecast asks for nothing; only the floor can fire.
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("2")))
    # 6 units already on order → inventory position is 8, above the reorder level.
    db.add(OpenIndent(item_id=item.id, store_id=store.id, as_of_date=today, quantity=Decimal("6")))
    db.add(ItemStoreSettings(item_id=item.id, store_id=store.id, reorder_level=5))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    # Bare closing stock (2) is below the reorder level (5), but position 2+6=8
    # is not, so nothing should be ordered.
    assert float(report.total_indent_qty) == 0.0


def test_reorder_floor_orders_only_the_shortfall_after_open_indents(db):
    from app.models.settings import ItemStoreSettings
    from app.models.consumption import OpenIndent

    store, item = _seed(db)
    today = date(2026, 4, 22)
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("2")))
    db.add(OpenIndent(item_id=item.id, store_id=store.id, as_of_date=today, quantity=Decimal("3")))
    db.add(ItemStoreSettings(item_id=item.id, store_id=store.id, reorder_level=10))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    # position = 2 + 3 = 5; shortfall to reorder level 10 is 5 (not 8).
    assert float(report.total_indent_qty) == pytest.approx(5.0, abs=0.01)


def test_min_stock_floor_accounts_for_open_indents(db):
    """Same rule for the minimum-stock floor."""
    from app.models.settings import ItemStoreSettings
    from app.models.consumption import OpenIndent

    store, item = _seed(db)
    today = date(2026, 4, 22)
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("4")))
    db.add(OpenIndent(item_id=item.id, store_id=store.id, as_of_date=today, quantity=Decimal("10")))
    db.add(ItemStoreSettings(item_id=item.id, store_id=store.id, min_stock=12))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    # position = 14 already exceeds min_stock 12 → nothing ordered
    # (previously ordered 12 - 4 = 8).
    assert float(report.total_indent_qty) == 0.0


def test_min_stock_floor_orders_shortfall_against_position(db):
    from app.models.settings import ItemStoreSettings
    from app.models.consumption import OpenIndent

    store, item = _seed(db)
    today = date(2026, 4, 22)
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("4")))
    db.add(OpenIndent(item_id=item.id, store_id=store.id, as_of_date=today, quantity=Decimal("2")))
    db.add(ItemStoreSettings(item_id=item.id, store_id=store.id, min_stock=20))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    # position = 6; shortfall to 20 is 14 (not 16).
    assert float(report.total_indent_qty) == pytest.approx(14.0, abs=0.01)
