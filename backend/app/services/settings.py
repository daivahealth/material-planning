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
    "request_type": "stock_indent",
}

# Keys resolved only from HospitalSettings (these columns exist only there)
HOSPITAL_ONLY_KEYS = {
    "fsn_period_days", "fsn_schedule_days",
    "projection_formula", "projection_formula_expr",
    "fsn_fast_threshold", "fsn_slow_threshold",
}

# Default source resolution order (highest → lowest priority).
DEFAULT_SOURCE_ORDER = ["item_store", "item", "category", "group", "store", "hospital"]
_VALID_SOURCES = set(DEFAULT_SOURCE_ORDER)


def _get(obj, key: str):
    return getattr(obj, key, None)


def _parse_priority(raw) -> list:
    """Turn a store's ``settings_priority`` CSV into an ordered source list.

    Only the levels the store explicitly configured are used — omitted levels
    are NOT consulted (a store may drop levels it doesn't want). Unknown and
    duplicate tokens are dropped. A blank/NULL value, or a value with no valid
    tokens, yields the full system default order.

    Note: hospital-only keys (FSN/projection), ``lead_time_days`` and
    ``planning_enabled`` are resolved by dedicated rules and are unaffected by
    dropping a level here; only the generic per-level settings are.
    """
    if not raw:
        return list(DEFAULT_SOURCE_ORDER)
    order: list = []
    for tok in str(raw).split(","):
        tok = tok.strip()
        if tok in _VALID_SOURCES and tok not in order:
            order.append(tok)
    return order or list(DEFAULT_SOURCE_ORDER)


def _resolve_planning_enabled(item_s, store_s, hospital_s) -> bool:
    if hospital_s and _get(hospital_s, "planning_enabled") is False:
        return False
    if store_s and _get(store_s, "planning_enabled") is False:
        return False
    if item_s and _get(item_s, "planning_enabled") is False:
        return False
    return True


def resolve_all(db: Session, item_id: int, store_id: int) -> dict:
    """Resolve all settings for a (item, store) pair in ≤8 DB gets.

    Most fields resolve by walking the store's configured source priority order
    (``StoreSettings.settings_priority``) and taking the first level that has a
    value; when unset the system default order applies. Exceptions:
      * hospital-only keys always come from the hospital;
      * ``lead_time_days`` uses a fixed store > item precedence (supplier lead
        time is applied later in indent._get_lead_time_days);
      * ``planning_enabled`` is disabled if any level disables it.
    """
    item_store_s = db.get(ItemStoreSettings, (item_id, store_id))
    item_s = db.get(ItemSettings, item_id)
    item = db.get(Item, item_id)
    cat_s = db.get(ItemCategorySettings, item.category_id) if item and item.category_id else None
    grp_s = db.get(ItemGroupSettings, item.group_id) if item and item.group_id else None
    store_s = db.get(StoreSettings, store_id)
    store = db.get(Store, store_id)
    hospital_s = db.get(HospitalSettings, store.hospital_id) if store else None

    sources = {
        "item_store": item_store_s,
        "item": item_s,
        "category": cat_s,
        "group": grp_s,
        "store": store_s,
        "hospital": hospital_s,
    }
    order = _parse_priority(_get(store_s, "settings_priority"))

    result: dict = {}
    for key in DEFAULTS:
        if key == "planning_enabled":
            result[key] = _resolve_planning_enabled(item_s, store_s, hospital_s)
            continue

        if key == "lead_time_days":
            # Store lead time takes precedence over item (and over the
            # supplier lead time resolved at runtime).
            val = _get(store_s, key)
            if val is None:
                val = _get(item_s, key)
            result[key] = val if val is not None else DEFAULTS[key]
            continue

        if key in HOSPITAL_ONLY_KEYS:
            result[key] = _get(hospital_s, key) if hospital_s else None
            if result[key] is None:
                result[key] = DEFAULTS[key]
            continue

        # Generic resolution: walk the configured source order, first hit wins.
        # A source that lacks the column simply returns None and is skipped.
        val = None
        for src in order:
            val = _get(sources[src], key)
            if val is not None:
                break
        result[key] = val if val is not None else DEFAULTS[key]

    # Expose the effective order for transparency (not a resolved quantity).
    result["settings_priority"] = order
    return result


def resolve(db: Session, item_id: int, store_id: int, key: str) -> Any:
    """Resolve a single key (convenience wrapper — uses resolve_all internally)."""
    return resolve_all(db, item_id, store_id).get(key, DEFAULTS.get(key))
