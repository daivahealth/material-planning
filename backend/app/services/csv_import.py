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
from app.models.item import Item, ItemGroup, ItemCategory
from app.models.store import Store


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
