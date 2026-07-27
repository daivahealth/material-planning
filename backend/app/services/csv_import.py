"""
CSV import service with per-row validation and error reporting.
"""
import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import BinaryIO, Optional

from sqlalchemy.orm import Session

from app.models.consumption import ConsumptionRecord, ClosingStock, OpenIndent
from app.models.surge import SurgeRecord, get_season, SeasonType
from app.models.item import Item, ItemGroup, ItemCategory, Supplier
from app.models.store import Store
from app.models.settings import StoreSettings, ItemSettings, ItemStoreSettings
from app.schemas.settings import (
    StoreSettingsCreate, ItemSettingsCreate, ItemStoreSettingsCreate,
)


def _find_item(db: Session, code: str) -> Optional[Item]:
    return db.query(Item).filter(Item.code == code).first()


def _find_store(db: Session, code: str) -> Optional[Store]:
    return db.query(Store).filter(Store.code == code).first()


def _parse_date(val: str) -> date:
    return date.fromisoformat(val.strip())


def _parse_qty(val: str) -> Decimal:
    return Decimal(val.strip())


def import_consumption(db: Session, file: BinaryIO) -> dict:
    """
    Expected columns: item_code, store_code, date (YYYY-MM-DD), quantity
    """
    required = {"item_code", "store_code", "date", "quantity"}
    content = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    if not required.issubset(set(reader.fieldnames or [])):
        return {"imported": 0, "errors": [{"row": 0, "message": f"Missing columns. Required: {required}"}]}

    imported, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            item = _find_item(db, row["item_code"].strip())
            if not item:
                raise ValueError(f"Item code '{row['item_code']}' not found")
            store = _find_store(db, row["store_code"].strip())
            if not store:
                raise ValueError(f"Store code '{row['store_code']}' not found")
            rec = ConsumptionRecord(
                item_id=item.id,
                store_id=store.id,
                date=_parse_date(row["date"]),
                quantity=_parse_qty(row["quantity"]),
            )
            db.add(rec)
            imported += 1
        except (ValueError, InvalidOperation, KeyError) as exc:
            errors.append({"row": i, "message": str(exc)})

    if imported:
        db.commit()
    return {"imported": imported, "errors": errors}


def import_closing_stock(db: Session, file: BinaryIO) -> dict:
    """
    Expected columns: item_code, store_code, date (YYYY-MM-DD), quantity
    """
    required = {"item_code", "store_code", "date", "quantity"}
    content = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    if not required.issubset(set(reader.fieldnames or [])):
        return {"imported": 0, "errors": [{"row": 0, "message": f"Missing columns. Required: {required}"}]}

    imported, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            item = _find_item(db, row["item_code"].strip())
            if not item:
                raise ValueError(f"Item code '{row['item_code']}' not found")
            store = _find_store(db, row["store_code"].strip())
            if not store:
                raise ValueError(f"Store code '{row['store_code']}' not found")
            rec = ClosingStock(
                item_id=item.id,
                store_id=store.id,
                date=_parse_date(row["date"]),
                quantity=_parse_qty(row["quantity"]),
            )
            db.add(rec)
            imported += 1
        except (ValueError, InvalidOperation, KeyError) as exc:
            errors.append({"row": i, "message": str(exc)})

    if imported:
        db.commit()
    return {"imported": imported, "errors": errors}


def import_surge(db: Session, file: BinaryIO) -> dict:
    """
    Expected columns: item_code, store_code, recorded_date, extra_qty, reason, season
    season must be one of: Summer, Monsoon, Winter, Festive (or leave blank to auto-detect)
    """
    required = {"item_code", "store_code", "recorded_date", "extra_qty", "reason"}
    content = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    if not required.issubset(set(reader.fieldnames or [])):
        return {"imported": 0, "errors": [{"row": 0, "message": f"Missing columns. Required: {required}"}]}

    valid_seasons = {s.value for s in SeasonType}
    imported, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            item = _find_item(db, row["item_code"].strip())
            if not item:
                raise ValueError(f"Item code '{row['item_code']}' not found")
            store = _find_store(db, row["store_code"].strip())
            if not store:
                raise ValueError(f"Store code '{row['store_code']}' not found")
            rec_date = _parse_date(row["recorded_date"])
            raw_season = (row.get("season") or "").strip()
            if raw_season and raw_season not in valid_seasons:
                raise ValueError(f"season must be one of {valid_seasons}")
            season = SeasonType(raw_season) if raw_season else get_season(rec_date.month)
            rec = SurgeRecord(
                item_id=item.id,
                store_id=store.id,
                recorded_date=rec_date,
                month=rec_date.month,
                season=season,
                reason=row["reason"].strip(),
                extra_qty=_parse_qty(row["extra_qty"]),
            )
            db.add(rec)
            imported += 1
        except (ValueError, InvalidOperation, KeyError) as exc:
            errors.append({"row": i, "message": str(exc)})

    if imported:
        db.commit()
    return {"imported": imported, "errors": errors}


def import_open_indent(db: Session, file: BinaryIO) -> dict:
    """
    Expected columns: item_code, store_code, as_of_date (YYYY-MM-DD), quantity, reference (optional)
    Each row represents a pending/open indent quantity that will be subtracted
    from projected requirements during indent generation.
    """
    required = {"item_code", "store_code", "as_of_date", "quantity"}
    content = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    if not required.issubset(set(reader.fieldnames or [])):
        return {"imported": 0, "errors": [{"row": 0, "message": f"Missing columns. Required: {required}"}]}

    imported, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            item = _find_item(db, row["item_code"].strip())
            if not item:
                raise ValueError(f"Item code '{row['item_code']}' not found")
            store = _find_store(db, row["store_code"].strip())
            if not store:
                raise ValueError(f"Store code '{row['store_code']}' not found")
            rec = OpenIndent(
                item_id=item.id,
                store_id=store.id,
                as_of_date=_parse_date(row["as_of_date"]),
                quantity=_parse_qty(row["quantity"]),
                reference=(row.get("reference") or "").strip() or None,
            )
            db.add(rec)
            imported += 1
        except (ValueError, InvalidOperation, KeyError) as exc:
            errors.append({"row": i, "message": str(exc)})

    if imported:
        db.commit()
    return {"imported": imported, "errors": errors}


# ---------------------------------------------------------------------------
# Settings uploads (store / item / item×store) and preferred-supplier mapping
#
# Semantics, identical for all settings uploads:
#   * Upsert — the settings row is created if absent, updated if present.
#   * Only columns PRESENT in the CSV header are considered; any settings field
#     not in the header is left untouched.
#   * A BLANK cell leaves that field unchanged (non-destructive default, so a
#     partially-filled sheet never wipes existing configuration).
#   * The literal token NULL (case-insensitive) CLEARS the field back to
#     "inherit" — the explicit way to remove an override.
#   * Values are validated through the same Pydantic schemas the UI uses, so a
#     CSV can never set something the Settings screen would reject.
# ---------------------------------------------------------------------------

_CLEAR_TOKEN = "null"


def _validate(schema_cls, updates: dict) -> None:
    """Run the UI's own Pydantic validation, re-raising a terse message.

    Pydantic's default text embeds the whole input dict and a docs URL, which is
    unreadable in a per-row CSV error list.
    """
    try:
        schema_cls(**updates)
    except Exception as exc:
        msgs = []
        for err in getattr(exc, "errors", lambda: [])():
            msg = err.get("msg", "")
            msgs.append(msg.replace("Value error, ", ""))
        raise ValueError("; ".join(msgs) or str(exc).split("\n")[0]) from exc

# field -> python type, per settings level
_STORE_SETTING_TYPES = {
    "indent_duration_days": int, "lookback_days": int, "lead_time_days": int,
    "forecast_method": str, "rolling_recent_weight_factor": float,
    "rolling_bucket_days": int, "planning_enabled": bool,
    "settings_priority": str, "request_type": str,
}
_ITEM_SETTING_TYPES = {
    "indent_duration_days": int, "pack_size": int, "lead_time_days": int,
    "safety_stock_days": float, "reorder_level": float, "min_stock": float,
    "max_stock": float, "lookback_days": int, "planning_enabled": bool,
}
_ITEM_STORE_SETTING_TYPES = {
    "indent_duration_days": int, "safety_stock_days": float,
    "reorder_level": float, "min_stock": float, "max_stock": float,
}


def _parse_bool(val: str) -> bool:
    v = val.strip().lower()
    if v in ("true", "1", "yes", "y"):
        return True
    if v in ("false", "0", "no", "n"):
        return False
    raise ValueError(f"'{val}' is not a valid true/false value")


def _coerce(field: str, raw: str, ftype) -> object:
    """Convert a CSV cell to the field's python type, with a clear error."""
    try:
        if ftype is bool:
            return _parse_bool(raw)
        if ftype is int:
            # tolerate "30" and "30.0"
            f = float(raw)
            if f != int(f):
                raise ValueError("must be a whole number")
            return int(f)
        if ftype is float:
            return float(raw)
        return raw.strip()
    except ValueError as exc:
        raise ValueError(f"{field}: {exc}") from exc


def _row_updates(row: dict, present: list, types: dict) -> dict:
    """Build {field: value} for one row. Blank = skip; NULL = clear."""
    updates = {}
    for f in present:
        raw = (row.get(f) or "").strip()
        if raw == "":
            continue                      # blank → leave unchanged
        if raw.lower() == _CLEAR_TOKEN:
            updates[f] = None             # NULL → clear to inherit
            continue
        updates[f] = _coerce(f, raw, types[f])
    return updates


def _read_csv(file: BinaryIO):
    content = file.read().decode("utf-8-sig")
    return csv.DictReader(io.StringIO(content))


def import_store_settings(db: Session, file: BinaryIO) -> dict:
    """
    Store-level settings. Required column: store_code.
    Optional: indent_duration_days, lookback_days, lead_time_days,
              forecast_method, rolling_recent_weight_factor, rolling_bucket_days,
              planning_enabled, settings_priority, request_type
    """
    reader = _read_csv(file)
    fields = set(reader.fieldnames or [])
    if "store_code" not in fields:
        return {"imported": 0, "errors": [{"row": 0, "message": "Missing required column: store_code"}]}
    present = [f for f in _STORE_SETTING_TYPES if f in fields]
    if not present:
        return {"imported": 0, "errors": [{"row": 0, "message":
                f"No settings columns found. Provide at least one of: {sorted(_STORE_SETTING_TYPES)}"}]}

    imported, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            store = _find_store(db, (row.get("store_code") or "").strip())
            if not store:
                raise ValueError(f"Store code '{row.get('store_code')}' not found")
            updates = _row_updates(row, present, _STORE_SETTING_TYPES)
            if not updates:
                continue
            _validate(StoreSettingsCreate, updates)   # same validation as the UI
            obj = db.get(StoreSettings, store.id)
            if obj is None:
                obj = StoreSettings(store_id=store.id)
                db.add(obj)
            for k, v in updates.items():
                setattr(obj, k, v)
            imported += 1
        except Exception as exc:
            errors.append({"row": i, "message": str(exc)})

    if imported:
        db.commit()
    return {"imported": imported, "errors": errors}


def import_item_settings(db: Session, file: BinaryIO) -> dict:
    """
    Item-level settings. Required column: item_code.
    Optional: indent_duration_days, pack_size, lead_time_days, safety_stock_days,
              reorder_level, min_stock, max_stock, lookback_days, planning_enabled
    """
    reader = _read_csv(file)
    fields = set(reader.fieldnames or [])
    if "item_code" not in fields:
        return {"imported": 0, "errors": [{"row": 0, "message": "Missing required column: item_code"}]}
    present = [f for f in _ITEM_SETTING_TYPES if f in fields]
    if not present:
        return {"imported": 0, "errors": [{"row": 0, "message":
                f"No settings columns found. Provide at least one of: {sorted(_ITEM_SETTING_TYPES)}"}]}

    imported, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            item = _find_item(db, (row.get("item_code") or "").strip())
            if not item:
                raise ValueError(f"Item code '{row.get('item_code')}' not found")
            updates = _row_updates(row, present, _ITEM_SETTING_TYPES)
            if not updates:
                continue
            _validate(ItemSettingsCreate, updates)
            obj = db.get(ItemSettings, item.id)
            if obj is None:
                obj = ItemSettings(item_id=item.id)
                db.add(obj)
            for k, v in updates.items():
                setattr(obj, k, v)
            imported += 1
        except Exception as exc:
            errors.append({"row": i, "message": str(exc)})

    if imported:
        db.commit()
    return {"imported": imported, "errors": errors}


def import_item_store_settings(db: Session, file: BinaryIO) -> dict:
    """
    Item × Store settings (highest priority level).
    Required columns: item_code, store_code.
    Optional: indent_duration_days, safety_stock_days, reorder_level,
              min_stock, max_stock
    """
    reader = _read_csv(file)
    fields = set(reader.fieldnames or [])
    missing = {"item_code", "store_code"} - fields
    if missing:
        return {"imported": 0, "errors": [{"row": 0, "message": f"Missing required column(s): {sorted(missing)}"}]}
    present = [f for f in _ITEM_STORE_SETTING_TYPES if f in fields]
    if not present:
        return {"imported": 0, "errors": [{"row": 0, "message":
                f"No settings columns found. Provide at least one of: {sorted(_ITEM_STORE_SETTING_TYPES)}"}]}

    imported, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            item = _find_item(db, (row.get("item_code") or "").strip())
            if not item:
                raise ValueError(f"Item code '{row.get('item_code')}' not found")
            store = _find_store(db, (row.get("store_code") or "").strip())
            if not store:
                raise ValueError(f"Store code '{row.get('store_code')}' not found")
            updates = _row_updates(row, present, _ITEM_STORE_SETTING_TYPES)
            if not updates:
                continue
            _validate(ItemStoreSettingsCreate, updates)
            obj = db.get(ItemStoreSettings, (item.id, store.id))
            if obj is None:
                obj = ItemStoreSettings(item_id=item.id, store_id=store.id)
                db.add(obj)
            for k, v in updates.items():
                setattr(obj, k, v)
            imported += 1
        except Exception as exc:
            errors.append({"row": i, "message": str(exc)})

    if imported:
        db.commit()
    return {"imported": imported, "errors": errors}


def import_preferred_suppliers(db: Session, file: BinaryIO) -> dict:
    """
    Item master — preferred supplier mapping.
    Required columns: item_code, supplier_code
    A blank supplier_code leaves the item unchanged; NULL clears the preferred
    supplier. Unlike the settings uploads this updates the Item master row.
    """
    reader = _read_csv(file)
    fields = set(reader.fieldnames or [])
    missing = {"item_code", "supplier_code"} - fields
    if missing:
        return {"imported": 0, "errors": [{"row": 0, "message": f"Missing required column(s): {sorted(missing)}"}]}

    imported, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            item = _find_item(db, (row.get("item_code") or "").strip())
            if not item:
                raise ValueError(f"Item code '{row.get('item_code')}' not found")
            raw = (row.get("supplier_code") or "").strip()
            if raw == "":
                continue                       # blank → leave unchanged
            if raw.lower() == _CLEAR_TOKEN:
                item.preferred_supplier_id = None
            else:
                sup = db.query(Supplier).filter(Supplier.code == raw).first()
                if not sup:
                    raise ValueError(f"Supplier code '{raw}' not found")
                item.preferred_supplier_id = sup.id
            imported += 1
        except Exception as exc:
            errors.append({"row": i, "message": str(exc)})

    if imported:
        db.commit()
    return {"imported": imported, "errors": errors}


def import_item_groups(db: Session, file: BinaryIO) -> dict:
    """
    Expected columns: name
    Skips rows where the group name already exists (upsert-safe).
    """
    required = {"name"}
    content = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    if not required.issubset(set(reader.fieldnames or [])):
        return {"imported": 0, "errors": [{"row": 0, "message": f"Missing columns. Required: {required}"}]}

    imported, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            name = row["name"].strip()
            if not name:
                raise ValueError("name cannot be empty")
            existing = db.query(ItemGroup).filter(ItemGroup.name == name).first()
            if existing:
                errors.append({"row": i, "message": f"Item group '{name}' already exists — skipped"})
                continue
            db.add(ItemGroup(name=name))
            imported += 1
        except (ValueError, KeyError) as exc:
            errors.append({"row": i, "message": str(exc)})

    if imported:
        db.commit()
    return {"imported": imported, "errors": errors}


def import_item_categories(db: Session, file: BinaryIO) -> dict:
    """
    Expected columns: name, is_vital (optional — true/false/1/0, default false)
    Skips rows where the category name already exists.
    """
    required = {"name"}
    content = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    if not required.issubset(set(reader.fieldnames or [])):
        return {"imported": 0, "errors": [{"row": 0, "message": f"Missing columns. Required: {required}"}]}

    imported, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            name = row["name"].strip()
            if not name:
                raise ValueError("name cannot be empty")
            existing = db.query(ItemCategory).filter(ItemCategory.name == name).first()
            if existing:
                errors.append({"row": i, "message": f"Item category '{name}' already exists — skipped"})
                continue
            raw_vital = (row.get("is_vital") or "").strip().lower()
            is_vital = raw_vital in ("true", "1", "yes")
            db.add(ItemCategory(name=name, is_vital=is_vital))
            imported += 1
        except (ValueError, KeyError) as exc:
            errors.append({"row": i, "message": str(exc)})

    if imported:
        db.commit()
    return {"imported": imported, "errors": errors}


def import_items(db: Session, file: BinaryIO) -> dict:
    """
    Expected columns: code, name, unit, group_name (optional), category_name (optional)
    Skips rows where the item code already exists.
    """
    required = {"code", "name", "unit"}
    content = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    if not required.issubset(set(reader.fieldnames or [])):
        return {"imported": 0, "errors": [{"row": 0, "message": f"Missing columns. Required: {required}"}]}

    imported, errors = 0, []
    for i, row in enumerate(reader, start=2):
        try:
            code = row["code"].strip()
            name = row["name"].strip()
            unit = row["unit"].strip()
            if not code or not name or not unit:
                raise ValueError("code, name, and unit cannot be empty")
            existing = db.query(Item).filter(Item.code == code).first()
            if existing:
                errors.append({"row": i, "message": f"Item code '{code}' already exists — skipped"})
                continue

            group_id = None
            raw_group = (row.get("group_name") or "").strip()
            if raw_group:
                grp = db.query(ItemGroup).filter(ItemGroup.name == raw_group).first()
                if not grp:
                    raise ValueError(f"Item group '{raw_group}' not found")
                group_id = grp.id

            category_id = None
            raw_cat = (row.get("category_name") or "").strip()
            if raw_cat:
                cat = db.query(ItemCategory).filter(ItemCategory.name == raw_cat).first()
                if not cat:
                    raise ValueError(f"Item category '{raw_cat}' not found")
                category_id = cat.id

            db.add(Item(code=code, name=name, unit=unit, group_id=group_id, category_id=category_id))
            imported += 1
        except (ValueError, KeyError) as exc:
            errors.append({"row": i, "message": str(exc)})

    if imported:
        db.commit()
    return {"imported": imported, "errors": errors}
