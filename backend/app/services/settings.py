"""
Settings resolution service.

Resolution hierarchy (highest → lowest priority):
  ItemStoreSettings (item+store specific)
  > ItemSettings (item specific)
  > ItemCategorySettings (item's category)
  > ItemGroupSettings (item's group)
  > StoreSettings (store specific)
  > HospitalSettings (hospital-wide)
  > DEFAULTS

Special rules:
  forecast_method / rolling_recent_weight_factor / rolling_bucket_days / trend_min_points:
      StoreSettings > HospitalSettings  (skip item/cat/group)
  fsn_period_days / fsn_schedule_days / projection_formula / projection_formula_expr /
      fsn_fast_threshold / fsn_slow_threshold:
      HospitalSettings only
  planning_enabled: any disabled level disables planning for that scope
"""

from typing import Any
from sqlalchemy.orm import Session

from app.models.settings import (
    HospitalSettings,
    StoreSettings,
    ItemSettings,
    ItemCategorySettings,
    ItemGroupSettings,
    ItemStoreSettings,
)
from app.models.item import Item
from app.models.store import Store

DEFAULTS: dict[str, Any] = {
    "lookback_days": 90,
    "safety_stock_days": 7.0,
    "reorder_level": None,
    "min_stock": None,
    "max_stock": None,
    "pack_size": 1,
    "lead_time_days": 0,
    "indent_duration_days": 30,
    "fsn_period_days": 365,
    "fsn_schedule_days": 30,
    "fsn_fast_threshold": 1.0,
    "fsn_slow_threshold": 0.1,
    "projection_formula": "standard",
    "projection_formula_expr": None,
    "forecast_method": "baseline_avg",
    "rolling_recent_weight_factor": 2.0,
    "rolling_bucket_days": 1,
    "trend_min_points": 7,
    "planning_enabled": True,
}

# Keys resolved only from HospitalSettings
HOSPITAL_ONLY_KEYS = {
    "fsn_period_days", "fsn_schedule_days",
    "projection_formula", "projection_formula_expr",
    "fsn_fast_threshold", "fsn_slow_threshold",
}

# Keys resolved from StoreSettings then HospitalSettings (skip item/cat/group)
STORE_HOSPITAL_KEYS = {
    "forecast_method", "rolling_recent_weight_factor",
    "rolling_bucket_days", "trend_min_points",
}

# Keys available at ItemStoreSettings level (item+store specific overrides)
ITEM_STORE_KEYS = {
    "indent_duration_days", "safety_stock_days",
    "reorder_level", "min_stock", "max_stock",
}


def _get(obj, key: str):
    return getattr(obj, key, None)


def _resolve_planning_enabled(item_s, store_s, hospital_s) -> bool:
    if hospital_s and _get(hospital_s, "planning_enabled") is False:
        return False
    if store_s and _get(store_s, "planning_enabled") is False:
        return False
    if item_s and _get(item_s, "planning_enabled") is False:
        return False
    return True


def resolve_all(db: Session, item_id: int, store_id: int) -> dict:
    """Resolve all settings for a (item, store) pair in ≤8 DB gets."""
    item_store_s = db.get(ItemStoreSettings, (item_id, store_id))
    item_s = db.get(ItemSettings, item_id)
    item = db.get(Item, item_id)
    cat_s = db.get(ItemCategorySettings, item.category_id) if item and item.category_id else None
    grp_s = db.get(ItemGroupSettings, item.group_id) if item and item.group_id else None
    store_s = db.get(StoreSettings, store_id)
    store = db.get(Store, store_id)
    hospital_s = db.get(HospitalSettings, store.hospital_id) if store else None

    result: dict = {}
    for key in DEFAULTS:
        if key == "planning_enabled":
            result[key] = _resolve_planning_enabled(item_s, store_s, hospital_s)
            continue

        if key in HOSPITAL_ONLY_KEYS:
            val = _get(hospital_s, key) if hospital_s else None

        elif key in STORE_HOSPITAL_KEYS:
            val = _get(store_s, key) if store_s else None
            if val is None:
                val = _get(hospital_s, key) if hospital_s else None

        elif key == "lead_time_days":
            # Item-level lead time override; supplier-based lead time handled
            # separately in indent._get_lead_time_days (which is called at runtime)
            # and its result takes over when ItemSettings.lead_time_days is None.
            val = _get(item_s, key) if item_s else None

        else:
            # Full hierarchy: item+store > item > cat > group > store > hospital
            val = _get(item_store_s, key) if item_store_s and key in ITEM_STORE_KEYS else None
            if val is None:
                val = _get(item_s, key) if item_s else None
            if val is None:
                val = _get(cat_s, key) if cat_s else None
            if val is None:
                val = _get(grp_s, key) if grp_s else None
            if val is None:
                val = _get(store_s, key) if store_s else None
            if val is None:
                val = _get(hospital_s, key) if hospital_s else None

        result[key] = val if val is not None else DEFAULTS[key]
    return result


def resolve(db: Session, item_id: int, store_id: int, key: str) -> Any:
    """Resolve a single key (convenience wrapper — uses resolve_all internally)."""
    return resolve_all(db, item_id, store_id).get(key, DEFAULTS.get(key))
