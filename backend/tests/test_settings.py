"""
Tests for SettingsResolutionService hierarchy.
"""
import pytest
from app.models.hospital import Hospital
from app.models.store import Store
from app.models.item import ItemGroup, ItemCategory, Item
from app.models.settings import (
    HospitalSettings, StoreSettings, ItemSettings,
    ItemCategorySettings, ItemGroupSettings,
)
from app.services.settings import resolve


def _setup_hierarchy(db):
    hospital = Hospital(name="Test Hospital", code="TH")
    db.add(hospital)
    db.flush()

    db.add(HospitalSettings(
        hospital_id=hospital.id, lookback_days=90, safety_stock_pct=0.10,
        indent_duration_days=30, fsn_period_days=365, fsn_schedule_days=30,
        projection_formula="standard",
    ))
    db.flush()

    store = Store(hospital_id=hospital.id, name="Pharmacy", code="PH")
    db.add(store)
    db.flush()

    group = ItemGroup(name="Pharma")
    category = ItemCategory(name="Antibiotics", is_vital=True)
    db.add_all([group, category])
    db.flush()

    item = Item(name="Drug A", code="DA", unit="Tabs", group_id=group.id, category_id=category.id)
    db.add(item)
    db.flush()

    return hospital, store, group, category, item


def test_resolves_hospital_default(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    val = resolve(db, item.id, store.id, "lookback_days")
    assert val == 90


def test_item_setting_overrides_hospital(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(ItemSettings(item_id=item.id, safety_stock_pct=0.25))
    db.flush()
    val = resolve(db, item.id, store.id, "safety_stock_pct")
    assert val == 0.25


def test_category_setting_used_when_no_item_setting(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(ItemCategorySettings(category_id=category.id, safety_stock_pct=0.18))
    db.flush()
    val = resolve(db, item.id, store.id, "safety_stock_pct")
    assert val == 0.18


def test_group_setting_used_when_no_item_or_category(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(ItemGroupSettings(group_id=group.id, safety_stock_pct=0.12))
    db.flush()
    val = resolve(db, item.id, store.id, "safety_stock_pct")
    assert val == 0.12


def test_item_overrides_category_and_group(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(ItemGroupSettings(group_id=group.id, safety_stock_pct=0.12))
    db.add(ItemCategorySettings(category_id=category.id, safety_stock_pct=0.18))
    db.add(ItemSettings(item_id=item.id, safety_stock_pct=0.30))
    db.flush()
    val = resolve(db, item.id, store.id, "safety_stock_pct")
    assert val == 0.30


def test_store_indent_duration_overrides_hospital(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(StoreSettings(store_id=store.id, indent_duration_days=7))
    db.flush()
    val = resolve(db, item.id, store.id, "indent_duration_days")
    assert val == 7


def test_fsn_period_always_from_hospital(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    # Even with item-level settings, fsn_period_days must come from hospital
    db.add(ItemSettings(item_id=item.id, safety_stock_pct=0.20))
    db.flush()
    val = resolve(db, item.id, store.id, "fsn_period_days")
    assert val == 365


def test_falls_back_to_default_when_no_settings(db):
    hospital = Hospital(name="H2", code="H2")
    db.add(hospital)
    db.flush()
    store = Store(hospital_id=hospital.id, name="S2", code="S2")
    db.add(store)
    db.flush()
    item = Item(name="X", code="X", unit="Nos")
    db.add(item)
    db.flush()
    val = resolve(db, item.id, store.id, "lookback_days")
    assert val == 90  # default
