import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.item import Item
from app.models.store import Store
from app.models.settings import (
    HospitalSettings, StoreSettings, ItemSettings,
    ItemCategorySettings, ItemGroupSettings, ItemStoreSettings, SupplierSettings,
)
from app.schemas.settings import (
    HospitalSettingsCreate, HospitalSettingsOut,
    StoreSettingsCreate, StoreSettingsOut,
    ItemSettingsCreate, ItemSettingsOut,
    ItemCategorySettingsCreate, ItemCategorySettingsOut,
    ItemGroupSettingsCreate, ItemGroupSettingsOut,
    ItemStoreSettingsCreate, ItemStoreSettingsOut,
    SupplierSettingsCreate, SupplierSettingsOut,
    ResolvedSettings,
)
from app.models.user import User
from app.services.csv_import import ITEM_STORE_CSV_COLUMNS, ITEM_STORE_SETTING_TYPES
from app.services import settings as settings_svc
from app.services import audit
from app.services.auth import get_current_user, require_master

router = APIRouter(
    prefix="/api/settings",
    tags=["Settings"],
    dependencies=[Depends(get_current_user)],
)


def _clean_payload(model, payload) -> dict:
    """Return the fields the client explicitly sent (``exclude_unset``), so a
    field sent as ``null`` clears the stored value instead of being ignored.
    A ``null`` is dropped only for NOT NULL columns, where writing it would
    violate the constraint or wipe a required default."""
    data = payload.model_dump(exclude_unset=True)
    cols = model.__table__.columns
    return {
        k: v for k, v in data.items()
        if not (v is None and k in cols and not cols[k].nullable)
    }


def _upsert(db, model, pk_field, pk_value, payload, entity=None, actor=None, request=None):
    """Create/update a settings row. Records an audit entry with the changed
    fields (before → after) in the same transaction as the change."""
    existing = db.get(model, pk_value)
    data = _clean_payload(model, payload)
    before = {k: getattr(existing, k, None) for k in data} if existing else {}
    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
    else:
        obj = model(**{pk_field: pk_value, **data})
        db.add(obj)
    if entity is not None:
        changes = audit.diff(before, data) if existing else {
            k: {"from": None, "to": audit._safe(v)} for k, v in data.items()
        }
        if changes:
            audit.record(
                db, actor, "update" if existing else "create", entity, pk_value,
                summary=(f"{'Updated' if existing else 'Created'} {entity} "
                         f"{pk_value}: {', '.join(sorted(changes))}"),
                details=changes, request=request,
            )
    db.commit()
    return db.get(model, pk_value)


@router.get("/resolve", response_model=ResolvedSettings)
def resolve_settings(item_id: int, store_id: int, db: Session = Depends(get_db)):
    return ResolvedSettings(
        item_id=item_id,
        store_id=store_id,
        settings=settings_svc.resolve_all(db, item_id, store_id),
    )


# ---- Hospital Settings ----
@router.get("/hospital/{hospital_id}", response_model=HospitalSettingsOut)
def get_hospital_settings(hospital_id: int, db: Session = Depends(get_db)):
    obj = db.get(HospitalSettings, hospital_id)
    if not obj:
        raise HTTPException(404, "Not found")
    return obj


@router.put("/hospital/{hospital_id}", response_model=HospitalSettingsOut)
def upsert_hospital_settings(
    hospital_id: int,
    payload: HospitalSettingsCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = _upsert(db, HospitalSettings, "hospital_id", hospital_id, payload, entity="hospital_settings",
                   actor=current_user, request=request)
    from app.scheduler import schedule_fsn_hospital, sync_hospital_store_indent_jobs
    hs = db.get(HospitalSettings, hospital_id)
    schedule_fsn_hospital(hospital_id, hs.fsn_schedule_days or 30)
    # The hospital default feeds every store that doesn't override it.
    sync_hospital_store_indent_jobs(db, hospital_id)
    return obj


# ---- Store Settings ----
@router.get("/store/{store_id}", response_model=StoreSettingsOut)
def get_store_settings(store_id: int, db: Session = Depends(get_db)):
    obj = db.get(StoreSettings, store_id)
    if not obj:
        raise HTTPException(404, "Not found")
    return obj


@router.put("/store/{store_id}", response_model=StoreSettingsOut)
def upsert_store_settings(
    store_id: int,
    payload: StoreSettingsCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = _upsert(db, StoreSettings, "store_id", store_id, payload, entity="store_settings",
                   actor=current_user, request=request)
    # Create/remove/reschedule the per-store indent job to match the saved
    # settings (both the on/off flag and the interval).
    from app.scheduler import sync_store_indent_job
    sync_store_indent_job(db, store_id)
    return obj


# ---- Item Settings ----
@router.get("/item/{item_id}", response_model=ItemSettingsOut)
def get_item_settings(item_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemSettings, item_id)
    if not obj:
        raise HTTPException(404, "Not found")
    return obj


@router.put("/item/{item_id}", response_model=ItemSettingsOut)
def upsert_item_settings(
    item_id: int,
    payload: ItemSettingsCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    return _upsert(db, ItemSettings, "item_id", item_id, payload, entity="item_settings",
                   actor=current_user, request=request)


# ---- Item+Store Settings ----
@router.get("/item-store/export")
def export_item_store_settings(
    store_id: Optional[int] = None,
    item_id: Optional[int] = None,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    """Export the configured Item × Store overrides as CSV.

    Columns are exactly those ``import_item_store_settings`` accepts, in the
    same order, so an exported file can be edited and re-imported unchanged.

    Only rows that exist are emitted — this table holds overrides, not the full
    item x store cross product. An unset (NULL) column exports as an EMPTY
    field, never ``0``/``false``: re-importing a blank leaves the override
    unset so the value keeps inheriting, whereas a literal 0 would pin it.
    """
    q = (
        db.query(
            Item.code.label("item_code"),
            Store.code.label("store_code"),
            ItemStoreSettings,
        )
        .join(Item, Item.id == ItemStoreSettings.item_id)
        .join(Store, Store.id == ItemStoreSettings.store_id)
    )
    if store_id is not None:
        q = q.filter(ItemStoreSettings.store_id == store_id)
    if item_id is not None:
        q = q.filter(ItemStoreSettings.item_id == item_id)
    rows = q.order_by(Store.code.asc(), Item.code.asc()).all()

    def _fmt(value, ftype):
        if value is None:
            return ""                       # unset -> blank, so it keeps inheriting
        if ftype is bool:
            return str(bool(value)).lower()  # import's _parse_bool accepts true/false
        if ftype is int:
            return int(value)
        f = float(value)
        return str(int(f)) if f.is_integer() else str(f)   # 7.0 -> "7"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(ITEM_STORE_CSV_COLUMNS)
    for item_code, store_code, s in rows:
        writer.writerow([item_code, store_code, *(
            _fmt(getattr(s, field, None), ftype)
            for field, ftype in ITEM_STORE_SETTING_TYPES.items()
        )])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=item_store_settings.csv"},
    )


@router.get("/item-store/{item_id}/{store_id}", response_model=ItemStoreSettingsOut)
def get_item_store_settings(item_id: int, store_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemStoreSettings, (item_id, store_id))
    if not obj:
        raise HTTPException(404, "Not found")
    return obj


@router.put("/item-store/{item_id}/{store_id}", response_model=ItemStoreSettingsOut)
def upsert_item_store_settings(
    item_id: int,
    store_id: int,
    payload: ItemStoreSettingsCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    existing = db.get(ItemStoreSettings, (item_id, store_id))
    data = _clean_payload(ItemStoreSettings, payload)
    before = {k: getattr(existing, k, None) for k in data} if existing else {}
    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
    else:
        obj = ItemStoreSettings(item_id=item_id, store_id=store_id, **data)
        db.add(obj)
    changes = audit.diff(before, data) if existing else {
        k: {"from": None, "to": audit._safe(v)} for k, v in data.items()
    }
    if changes:
        audit.record(
            db, current_user, "update" if existing else "create",
            "item_store_settings", f"{item_id}:{store_id}",
            summary=(f"{'Updated' if existing else 'Created'} item_store_settings "
                     f"item={item_id} store={store_id}: {', '.join(sorted(changes))}"),
            details=changes, request=request,
        )
    db.commit()
    return db.get(ItemStoreSettings, (item_id, store_id))


# ---- Category Settings ----
@router.get("/category/{category_id}", response_model=ItemCategorySettingsOut)
def get_category_settings(category_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemCategorySettings, category_id)
    if not obj:
        raise HTTPException(404, "Not found")
    return obj


@router.put("/category/{category_id}", response_model=ItemCategorySettingsOut)
def upsert_category_settings(
    category_id: int,
    payload: ItemCategorySettingsCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    return _upsert(db, ItemCategorySettings, "category_id", category_id, payload, entity="item_category_settings",
                   actor=current_user, request=request)


# ---- Group Settings ----
@router.get("/group/{group_id}", response_model=ItemGroupSettingsOut)
def get_group_settings(group_id: int, db: Session = Depends(get_db)):
    obj = db.get(ItemGroupSettings, group_id)
    if not obj:
        raise HTTPException(404, "Not found")
    return obj


@router.put("/group/{group_id}", response_model=ItemGroupSettingsOut)
def upsert_group_settings(
    group_id: int,
    payload: ItemGroupSettingsCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    return _upsert(db, ItemGroupSettings, "group_id", group_id, payload, entity="item_group_settings",
                   actor=current_user, request=request)


# ---- Supplier Settings ----
@router.get("/supplier/{supplier_id}", response_model=SupplierSettingsOut)
def get_supplier_settings(supplier_id: int, db: Session = Depends(get_db)):
    obj = db.get(SupplierSettings, supplier_id)
    if not obj:
        raise HTTPException(404, "Not found")
    return obj


@router.put("/supplier/{supplier_id}", response_model=SupplierSettingsOut)
def upsert_supplier_settings(
    supplier_id: int,
    payload: SupplierSettingsCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    return _upsert(db, SupplierSettings, "supplier_id", supplier_id, payload, entity="supplier_settings",
                   actor=current_user, request=request)
