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
from app.schemas.settings import HospitalSettingsCreate


def _setup_hierarchy(db):
    hospital = Hospital(name="Test Hospital", code="TH")
    db.add(hospital)
    db.flush()

    db.add(HospitalSettings(
        hospital_id=hospital.id, lookback_days=90, safety_stock_days=7.0,
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
    db.add(ItemSettings(item_id=item.id, safety_stock_days=5.0))
    db.flush()
    val = resolve(db, item.id, store.id, "safety_stock_days")
    assert val == 5.0


def test_category_setting_used_when_no_item_setting(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(ItemCategorySettings(category_id=category.id, safety_stock_days=4.0))
    db.flush()
    val = resolve(db, item.id, store.id, "safety_stock_days")
    assert val == 4.0


def test_group_setting_used_when_no_item_or_category(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(ItemGroupSettings(group_id=group.id, safety_stock_days=3.0))
    db.flush()
    val = resolve(db, item.id, store.id, "safety_stock_days")
    assert val == 3.0


def test_item_overrides_category_and_group(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(ItemGroupSettings(group_id=group.id, safety_stock_days=3.0))
    db.add(ItemCategorySettings(category_id=category.id, safety_stock_days=4.0))
    db.add(ItemSettings(item_id=item.id, safety_stock_days=6.0))
    db.flush()
    val = resolve(db, item.id, store.id, "safety_stock_days")
    assert val == 6.0


def test_store_indent_duration_overrides_hospital(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(StoreSettings(store_id=store.id, indent_duration_days=7))
    db.flush()
    val = resolve(db, item.id, store.id, "indent_duration_days")
    assert val == 7


def test_fsn_period_always_from_hospital(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    # Even with item-level settings, fsn_period_days must come from hospital
    db.add(ItemSettings(item_id=item.id, safety_stock_days=2.0))
    db.flush()
    val = resolve(db, item.id, store.id, "fsn_period_days")
    assert val == 365


def test_forecast_method_keys_always_from_hospital(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    hs = db.query(HospitalSettings).filter(HospitalSettings.hospital_id == hospital.id).first()
    hs.forecast_method = "weighted_rolling"
    hs.rolling_recent_weight_factor = 2.5
    hs.trend_min_points = 9
    db.flush()

    assert resolve(db, item.id, store.id, "forecast_method") == "weighted_rolling"
    assert resolve(db, item.id, store.id, "rolling_recent_weight_factor") == pytest.approx(2.5)
    assert resolve(db, item.id, store.id, "trend_min_points") == 9


def test_planning_enabled_default_true(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    assert resolve(db, item.id, store.id, "planning_enabled") is True


def test_planning_disabled_at_hospital_disables_effective_planning(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    hs = db.query(HospitalSettings).filter(HospitalSettings.hospital_id == hospital.id).first()
    hs.planning_enabled = False
    db.flush()

    assert resolve(db, item.id, store.id, "planning_enabled") is False


def test_planning_disabled_at_store_disables_effective_planning(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(StoreSettings(store_id=store.id, planning_enabled=False))
    db.flush()

    assert resolve(db, item.id, store.id, "planning_enabled") is False


def test_planning_disabled_at_item_disables_effective_planning(db):
    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(ItemSettings(item_id=item.id, planning_enabled=False))
    db.flush()

    assert resolve(db, item.id, store.id, "planning_enabled") is False


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


def test_hospital_settings_schema_rejects_invalid_forecast_method():
    with pytest.raises(ValueError):
        HospitalSettingsCreate(forecast_method="unknown_method")


def test_hospital_settings_schema_rejects_invalid_rolling_inputs():
    with pytest.raises(ValueError):
        HospitalSettingsCreate(forecast_method="weighted_rolling", rolling_bucket_days=0)

    with pytest.raises(ValueError):
        HospitalSettingsCreate(forecast_method="weighted_rolling", rolling_recent_weight_factor=0.9)

    with pytest.raises(ValueError):
        HospitalSettingsCreate(forecast_method="trend_adjusted", trend_min_points=1)


def test_item_store_pack_size_overrides_item(db):
    """Pack size can be set per item x store and beats the item-level value."""
    from app.models.settings import ItemStoreSettings

    hospital, store, group, category, item = _setup_hierarchy(db)
    db.add(ItemSettings(item_id=item.id, pack_size=10))
    db.flush()
    assert resolve(db, item.id, store.id, "pack_size") == 10

    db.add(ItemStoreSettings(item_id=item.id, store_id=store.id, pack_size=25))
    db.flush()
    assert resolve(db, item.id, store.id, "pack_size") == 25


# ─────────────────────────────────────────────────────────────
# indent_duration_days must describe a real coverage window
# ─────────────────────────────────────────────────────────────

def test_zero_indent_duration_is_rejected_on_write():
    """0 would make period_end land before period_start."""
    import pytest
    from pydantic import ValidationError
    from app.schemas.settings import (
        HospitalSettingsCreate, StoreSettingsCreate, ItemSettingsCreate,
        ItemCategorySettingsCreate, ItemGroupSettingsCreate, ItemStoreSettingsCreate,
    )
    for cls in (HospitalSettingsCreate, StoreSettingsCreate, ItemSettingsCreate,
                ItemCategorySettingsCreate, ItemGroupSettingsCreate, ItemStoreSettingsCreate):
        with pytest.raises(ValidationError):
            cls(indent_duration_days=0)
        with pytest.raises(ValidationError):
            cls(indent_duration_days=-5)
        # valid values and "unset" must still pass
        assert cls(indent_duration_days=30).indent_duration_days == 30
        assert cls().indent_duration_days is None


def test_legacy_zero_indent_duration_is_still_readable():
    """Out schemas must not reject a stored 0, or the row can't be corrected."""
    from app.schemas.settings import StoreSettingsOut, ItemStoreSettingsOut
    assert StoreSettingsOut(store_id=1, indent_duration_days=0).indent_duration_days == 0
    assert ItemStoreSettingsOut(item_id=1, store_id=1, indent_duration_days=0).indent_duration_days == 0


def test_legacy_zero_indent_duration_clamped_at_resolution(db):
    """A stored 0 must not propagate into the calculation."""
    from app.models.settings import StoreSettings
    from app.services.settings import resolve_from_sources, DEFAULTS

    s = resolve_from_sources(store_s=StoreSettings(store_id=1, indent_duration_days=0))
    assert s["indent_duration_days"] == DEFAULTS["indent_duration_days"]


def test_period_end_is_after_period_start_with_legacy_zero(db):
    """End-to-end: a legacy 0 must not produce a backwards period."""
    from datetime import date
    from decimal import Decimal
    from app.models.hospital import Hospital
    from app.models.store import Store
    from app.models.item import Item
    from app.models.settings import StoreSettings
    from app.models.consumption import ClosingStock
    from app.services.indent import generate_indent

    h = Hospital(code="H1", name="H"); db.add(h); db.flush()
    st = Store(code="S1", name="Store 1", hospital_id=h.id); db.add(st)
    it = Item(code="I1", name="Item 1"); db.add(it); db.flush()
    db.add(StoreSettings(store_id=st.id, indent_duration_days=0))
    db.add(ClosingStock(item_id=it.id, store_id=st.id, date=date(2026, 8, 19), quantity=Decimal("5")))
    db.flush()

    r = generate_indent(db, it.id, st.id, date(2026, 8, 19))
    assert r.period_end > r.period_start, f"backwards period: {r.period_start} -> {r.period_end}"


# ─────────────────────────────────────────────────────────────
# planning_enabled at item × store level
# ─────────────────────────────────────────────────────────────

def test_item_store_planning_disabled_resolves_false():
    from app.models.settings import ItemStoreSettings
    from app.services.settings import resolve_from_sources

    s = resolve_from_sources(item_store_s=ItemStoreSettings(item_id=1, store_id=1, planning_enabled=False))
    assert s["planning_enabled"] is False


def test_item_store_planning_true_cannot_override_a_broader_disable():
    """Veto semantics: any explicit False wins, regardless of settings_priority."""
    from app.models.settings import ItemStoreSettings, ItemSettings, StoreSettings, HospitalSettings
    from app.services.settings import resolve_from_sources

    on = ItemStoreSettings(item_id=1, store_id=1, planning_enabled=True)
    for broader in (dict(item_s=ItemSettings(item_id=1, planning_enabled=False)),
                    dict(store_s=StoreSettings(store_id=1, planning_enabled=False)),
                    dict(hospital_s=HospitalSettings(hospital_id=1, planning_enabled=False))):
        assert resolve_from_sources(item_store_s=on, **broader)["planning_enabled"] is False


def test_item_store_planning_unset_inherits_enabled():
    from app.models.settings import ItemStoreSettings
    from app.services.settings import resolve_from_sources

    assert resolve_from_sources(item_store_s=ItemStoreSettings(item_id=1, store_id=1))["planning_enabled"] is True
    assert resolve_from_sources()["planning_enabled"] is True


def test_item_store_planning_disabled_excludes_only_that_store(db):
    """Disabled for (item, store A) → no line at A, normal line at store B."""
    from datetime import date, timedelta
    from decimal import Decimal
    from app.models.hospital import Hospital
    from app.models.store import Store
    from app.models.item import Item
    from app.models.settings import HospitalSettings, ItemStoreSettings
    from app.models.consumption import ConsumptionRecord, ClosingStock
    from app.models.indent import IndentReport, TriggerType
    from app.services.indent import generate_batch

    today = date(2026, 9, 15)
    h = Hospital(code="H1", name="H"); db.add(h); db.flush()
    db.add(HospitalSettings(hospital_id=h.id, lookback_days=30, indent_duration_days=30,
                            safety_stock_days=3.0, fsn_period_days=365, fsn_schedule_days=30,
                            projection_formula="standard"))
    a = Store(hospital_id=h.id, code="A", name="A"); b = Store(hospital_id=h.id, code="B", name="B")
    it = Item(code="I1", name="Item", unit="Ea")
    db.add_all([a, b, it]); db.flush()
    for st in (a, b):
        for d in range(30):
            db.add(ConsumptionRecord(item_id=it.id, store_id=st.id,
                                     date=today - timedelta(days=30 - d), quantity=Decimal("10")))
        db.add(ClosingStock(item_id=it.id, store_id=st.id, date=today, quantity=Decimal("5")))
    db.add(ItemStoreSettings(item_id=it.id, store_id=a.id, planning_enabled=False))
    db.flush()

    rep_a, skip_a = generate_batch(db, a.id, today, TriggerType.api)
    rep_b, skip_b = generate_batch(db, b.id, today, TriggerType.api)

    assert (len(rep_a), skip_a) == (0, 1)
    assert (len(rep_b), skip_b) == (1, 0)
    assert db.query(IndentReport).filter(IndentReport.store_id == a.id).count() == 0
    assert float(rep_b[0].total_indent_qty) > 0


def test_item_store_planning_enabled_schema_and_csv_import(db):
    import io
    from app.models.hospital import Hospital
    from app.models.store import Store
    from app.models.item import Item
    from app.models.settings import ItemStoreSettings
    from app.schemas.settings import ItemStoreSettingsCreate, ItemStoreSettingsOut
    from app.services.csv_import import import_item_store_settings

    assert ItemStoreSettingsCreate(planning_enabled=False).planning_enabled is False
    assert ItemStoreSettingsOut(item_id=1, store_id=1, planning_enabled=False).planning_enabled is False

    h = Hospital(code="H1", name="H"); db.add(h); db.flush()
    st = Store(hospital_id=h.id, code="S1", name="S"); db.add(st)
    i1 = Item(code="I1", name="One", unit="Ea"); i2 = Item(code="I2", name="Two", unit="Ea")
    db.add_all([i1, i2]); db.flush()

    csv = b"item_code,store_code,planning_enabled\nI1,S1,false\nI2,S1,true\n"
    res = import_item_store_settings(db, io.BytesIO(csv))
    assert not res["errors"], res["errors"]
    assert db.get(ItemStoreSettings, (i1.id, st.id)).planning_enabled is False
    assert db.get(ItemStoreSettings, (i2.id, st.id)).planning_enabled is True
