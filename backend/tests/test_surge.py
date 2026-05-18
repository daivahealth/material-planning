"""
Tests for SurgePatternService integration within indent generation.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.models.hospital import Hospital
from app.models.store import Store
from app.models.item import Item
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
    item = Item(name="D", code="D", unit="Nos")
    db.add(item)
    db.flush()
    return store, item


def test_surge_matched_by_month(db):
    store, item = _seed(db)
    today = date(2026, 4, 22)  # indent period will be May (month 5)
    # next period starts May 1 → target_month=5
    today_for_test = date(2026, 4, 30)  # so next period is May
    for d in range(30):
        db.add(ConsumptionRecord(
            item_id=item.id, store_id=store.id,
            date=today_for_test - timedelta(days=30 - d),
            quantity=Decimal("10"),
        ))
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today_for_test, quantity=Decimal("0")))
    # Surge recorded in May last year
    db.add(SurgeRecord(
        item_id=item.id, store_id=store.id,
        recorded_date=date(2025, 5, 1), month=5,
        season=SeasonType.Summer, reason="May spike", extra_qty=Decimal("150"),
    ))
    db.flush()

    report = generate_indent(db, item.id, store.id, today_for_test)
    assert float(report.surge_indent_qty) == pytest.approx(150.0, abs=0.01)


def test_surge_matched_by_season(db):
    store, item = _seed(db)
    today = date(2026, 4, 22)  # Summer
    for d in range(30):
        db.add(ConsumptionRecord(
            item_id=item.id, store_id=store.id,
            date=today - timedelta(days=30 - d),
            quantity=Decimal("10"),
        ))
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("0")))
    # Surge recorded in March (Summer season, different month)
    db.add(SurgeRecord(
        item_id=item.id, store_id=store.id,
        recorded_date=date(2025, 3, 10), month=3,
        season=SeasonType.Summer, reason="Summer general spike", extra_qty=Decimal("80"),
    ))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    assert float(report.surge_indent_qty) == pytest.approx(80.0, abs=0.01)


def test_no_surge_when_different_season(db):
    store, item = _seed(db)
    today = date(2026, 4, 22)  # Summer
    for d in range(30):
        db.add(ConsumptionRecord(
            item_id=item.id, store_id=store.id,
            date=today - timedelta(days=30 - d),
            quantity=Decimal("10"),
        ))
    db.add(ClosingStock(item_id=item.id, store_id=store.id, date=today, quantity=Decimal("0")))
    # Surge only in Winter — should NOT apply to Summer indent
    db.add(SurgeRecord(
        item_id=item.id, store_id=store.id,
        recorded_date=date(2025, 12, 1), month=12,
        season=SeasonType.Winter, reason="Winter spike only", extra_qty=Decimal("200"),
    ))
    db.flush()

    report = generate_indent(db, item.id, store.id, today)
    assert float(report.surge_indent_qty) == 0.0
