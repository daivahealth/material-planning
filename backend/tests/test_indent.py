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
        safety_stock_pct=0.10, fsn_period_days=365, fsn_schedule_days=30,
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
