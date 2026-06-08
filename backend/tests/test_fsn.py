"""
Tests for FSN classification service.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.models.hospital import Hospital
from app.models.store import Store
from app.models.item import Item
from app.models.settings import HospitalSettings
from app.models.consumption import ConsumptionRecord
from app.models.classification import FSNClass
from app.services.fsn import compute_fsn_for_hospital


def _seed(db):
    hospital = Hospital(name="H", code="H")
    db.add(hospital)
    db.flush()
    db.add(HospitalSettings(
        hospital_id=hospital.id, lookback_days=90, indent_duration_days=30,
        safety_stock_pct=0.10, fsn_period_days=30,  # 30-day FSN period for quick test
        fsn_schedule_days=30, fsn_fast_threshold=2.0, fsn_slow_threshold=0.2,
        projection_formula="standard",
    ))
    store = Store(hospital_id=hospital.id, name="S", code="S")
    db.add(store)
    db.flush()
    return hospital, store


def test_fast_item_classified_F(db):
    hospital, store = _seed(db)
    item = Item(name="High Drug", code="HD", unit="Tabs")
    db.add(item)
    db.flush()
    today = date.today()
    for d in range(30):
        db.add(ConsumptionRecord(
            item_id=item.id, store_id=store.id,
            date=today - timedelta(days=29 - d),
            quantity=Decimal("100"),  # 100/day >> fast_threshold=2.0
        ))
    db.flush()
    compute_fsn_for_hospital(db, hospital.id)
    from app.models.classification import FSNClassification
    rec = db.query(FSNClassification).filter(
        FSNClassification.item_id == item.id,
        FSNClassification.store_id == store.id,
    ).first()
    assert rec is not None
    assert rec.classification == FSNClass.F


def test_zero_consumption_classified_N(db):
    hospital, store = _seed(db)
    item = Item(name="Zero Drug", code="ZD", unit="Tabs")
    db.add(item)
    db.flush()
    # No consumption records
    compute_fsn_for_hospital(db, hospital.id)
    from app.models.classification import FSNClassification
    rec = db.query(FSNClassification).filter(
        FSNClassification.item_id == item.id,
        FSNClassification.store_id == store.id,
    ).first()
    assert rec is not None
    assert rec.classification == FSNClass.N


def test_medium_consumption_classified_S(db):
    hospital, store = _seed(db)
    item = Item(name="Med Drug", code="MD", unit="Tabs")
    db.add(item)
    db.flush()
    today = date.today()
    # avg_daily ≈ 1.0, between slow(0.2) and fast(2.0) → S
    for d in range(30):
        db.add(ConsumptionRecord(
            item_id=item.id, store_id=store.id,
            date=today - timedelta(days=29 - d),
            quantity=Decimal("1"),
        ))
    db.flush()
    compute_fsn_for_hospital(db, hospital.id)
    from app.models.classification import FSNClassification
    rec = db.query(FSNClassification).filter(
        FSNClassification.item_id == item.id,
        FSNClassification.store_id == store.id,
    ).first()
    assert rec is not None
    assert rec.classification == FSNClass.S
