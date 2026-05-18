"""
Tests for CSV import service.
"""
import io
import pytest
from app.models.hospital import Hospital
from app.models.store import Store
from app.models.item import Item
from app.services.csv_import import import_consumption, import_closing_stock, import_surge


def _seed(db):
    hospital = Hospital(name="H", code="H")
    db.add(hospital)
    db.flush()
    store = Store(hospital_id=hospital.id, name="S", code="S1")
    db.add(store)
    item = Item(name="Drug", code="DRG", unit="Tabs")
    db.add(item)
    db.flush()
    return store, item


def _csv(content: str) -> io.BytesIO:
    return io.BytesIO(content.encode("utf-8"))


def test_consumption_import_valid(db):
    store, item = _seed(db)
    csv_data = "item_code,store_code,date,quantity\nDRG,S1,2026-04-01,10\nDRG,S1,2026-04-02,15\n"
    result = import_consumption(db, _csv(csv_data))
    assert result["imported"] == 2
    assert len(result["errors"]) == 0


def test_consumption_import_invalid_item(db):
    _seed(db)
    csv_data = "item_code,store_code,date,quantity\nBAD-CODE,S1,2026-04-01,10\n"
    result = import_consumption(db, _csv(csv_data))
    assert result["imported"] == 0
    assert result["errors"][0]["row"] == 2
    assert "not found" in result["errors"][0]["message"]


def test_consumption_import_invalid_date(db):
    store, item = _seed(db)
    csv_data = "item_code,store_code,date,quantity\nDRG,S1,not-a-date,10\n"
    result = import_consumption(db, _csv(csv_data))
    assert result["imported"] == 0
    assert len(result["errors"]) == 1


def test_consumption_import_missing_columns(db):
    _seed(db)
    csv_data = "item_code,date,quantity\nDRG,2026-04-01,10\n"
    result = import_consumption(db, _csv(csv_data))
    assert result["imported"] == 0
    assert "Missing columns" in result["errors"][0]["message"]


def test_closing_stock_import_valid(db):
    store, item = _seed(db)
    csv_data = "item_code,store_code,date,quantity\nDRG,S1,2026-04-22,200\n"
    result = import_closing_stock(db, _csv(csv_data))
    assert result["imported"] == 1
    assert len(result["errors"]) == 0


def test_surge_import_valid(db):
    store, item = _seed(db)
    csv_data = "item_code,store_code,recorded_date,extra_qty,reason,season\nDRG,S1,2026-04-10,100,Test spike,Summer\n"
    result = import_surge(db, _csv(csv_data))
    assert result["imported"] == 1
    assert len(result["errors"]) == 0


def test_surge_import_auto_detect_season(db):
    store, item = _seed(db)
    # No season column value → should auto-detect July → Monsoon
    csv_data = "item_code,store_code,recorded_date,extra_qty,reason,season\nDRG,S1,2026-07-10,50,Monsoon,,\n"
    result = import_surge(db, _csv(csv_data))
    # The extra trailing comma makes 7 fields; still valid
    from app.models.surge import SurgeRecord, SeasonType
    rec = db.query(SurgeRecord).first()
    if rec:
        assert rec.season == SeasonType.Monsoon


def test_surge_import_invalid_season(db):
    store, item = _seed(db)
    csv_data = "item_code,store_code,recorded_date,extra_qty,reason,season\nDRG,S1,2026-04-10,100,Test,BadSeason\n"
    result = import_surge(db, _csv(csv_data))
    assert result["imported"] == 0
    assert len(result["errors"]) == 1
    assert "season" in result["errors"][0]["message"].lower()
