"""
Settings resolution service.

Resolution order for most settings:
  ItemSettings > ItemCategorySettings > ItemGroupSettings > StoreSettings > HospitalSettings > default

Special rules:
  indent_duration_days: StoreSettings > HospitalSettings
  fsn_period_days / fsn_schedule_days: HospitalSettings only
  projection_formula / projection_formula_expr: HospitalSettings only
"""

from typing import Any, Optional
from sqlalchemy.orm import Session

from app.models.settings import (
    HospitalSettings,
    StoreSettings,
    ItemSettings,
    ItemCategorySettings,
    ItemGroupSettings,
)
from app.models.item import Item
from app.models.store import Store

DEFAULTS = {
    "lookback_days": 90,
    "safety_stock_pct": 0.10,
    "reorder_level": None,
    "min_stock": None,
    "max_stock": None,
    "indent_duration_days": 30,
    "fsn_period_days": 365,
    "fsn_schedule_days": 30,
    "fsn_fast_threshold": 1.0,
    "fsn_slow_threshold": 0.1,
    "projection_formula": "standard",
    "projection_formula_expr": None,
}

# Keys that only live at hospital level — do not walk item/category/group/store
HOSPITAL_ONLY_KEYS = {"fsn_period_days", "fsn_schedule_days", "projection_formula", "projection_formula_expr",
                      "fsn_fast_threshold", "fsn_slow_threshold"}

# Keys that resolve store > hospital (skip item/category/group)
STORE_HOSPITAL_KEYS = {"indent_duration_days"}


def _get(obj, key: str):
    val = getattr(obj, key, None)
    return val  # returns None if not present or None


def resolve(db: Session, item_id: int, store_id: int, key: str) -> Any:
    """Resolve a single settings key for a given (item, store) pair."""

    if key in HOSPITAL_ONLY_KEYS:
        store = db.get(Store, store_id)
        if store is None:
            return DEFAULTS.get(key)
        hospital_s = db.get(HospitalSettings, store.hospital_id)
        if hospital_s:
            val = _get(hospital_s, key)
            if val is not None:
                return val
        return DEFAULTS.get(key)

    if key in STORE_HOSPITAL_KEYS:
        store_s = db.get(StoreSettings, store_id)
        if store_s:
            val = _get(store_s, key)
            if val is not None:
                return val
        store = db.get(Store, store_id)
        if store:
            hospital_s = db.get(HospitalSettings, store.hospital_id)
            if hospital_s:
                val = _get(hospital_s, key)
                if val is not None:
                    return val
        return DEFAULTS.get(key)

    # Full hierarchy: item > category > group > store > hospital
    item_s = db.get(ItemSettings, item_id)
    if item_s:
        val = _get(item_s, key)
        if val is not None:
            return val

    item = db.get(Item, item_id)
    if item:
        if item.category_id:
            cat_s = db.get(ItemCategorySettings, item.category_id)
            if cat_s:
                val = _get(cat_s, key)
                if val is not None:
                    return val

        if item.group_id:
            grp_s = db.get(ItemGroupSettings, item.group_id)
            if grp_s:
                val = _get(grp_s, key)
                if val is not None:
                    return val

    store_s = db.get(StoreSettings, store_id)
    if store_s:
        val = _get(store_s, key)
        if val is not None:
            return val

    store = db.get(Store, store_id)
    if store:
        hospital_s = db.get(HospitalSettings, store.hospital_id)
        if hospital_s:
            val = _get(hospital_s, key)
            if val is not None:
                return val

    return DEFAULTS.get(key)


def resolve_all(db: Session, item_id: int, store_id: int) -> dict:
    """Resolve all known settings keys at once for (item, store).

    Loads each settings/entity object exactly once (≤7 DB gets) then resolves
    all keys from the cached objects — avoids the previous 12×7 = 84 DB round-
    trips that the old per-key resolve() loop produced.
    """
    # Load every relevant object once
    item_s = db.get(ItemSettings, item_id)
    item = db.get(Item, item_id)
    cat_s = db.get(ItemCategorySettings, item.category_id) if item and item.category_id else None
    grp_s = db.get(ItemGroupSettings, item.group_id) if item and item.group_id else None
    store_s = db.get(StoreSettings, store_id)
    store = db.get(Store, store_id)
    hospital_s = db.get(HospitalSettings, store.hospital_id) if store else None

    result: dict = {}
    for key in DEFAULTS:
        if key in HOSPITAL_ONLY_KEYS:
            val = _get(hospital_s, key) if hospital_s else None
        elif key in STORE_HOSPITAL_KEYS:
            val = _get(store_s, key) if store_s else None
            if val is None:
                val = _get(hospital_s, key) if hospital_s else None
        else:
            # Full hierarchy: item > category > group > store > hospital
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
