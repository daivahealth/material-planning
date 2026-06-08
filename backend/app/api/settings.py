from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db import get_db
from app.models.settings import (
    HospitalSettings, StoreSettings, ItemSettings,
    ItemCategorySettings, ItemGroupSettings, SupplierSettings,
)
from app.schemas.settings import (
    HospitalSettingsCreate, HospitalSettingsOut,
    StoreSettingsCreate, StoreSettingsOut,
    ItemSettingsCreate, ItemSettingsOut,
    ItemCategorySettingsCreate, ItemCategorySettingsOut,
    ItemGroupSettingsCreate, ItemGroupSettingsOut,
    SupplierSettingsCreate, SupplierSettingsOut,
    ResolvedSettings,
)
from app.models.user import User
from app.services import settings as settings_svc
from app.services.auth import get_current_user, require_master

router = APIRouter(
    prefix="/api/settings",
    tags=["Settings"],
    dependencies=[Depends(get_current_user)],
)


def _upsert(db, model, pk_field, pk_value, payload):
    existing = db.get(model, pk_value)
    data = payload.model_dump(exclude_none=True)
    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
    else:
        obj = model(**{pk_field: pk_value, **data})
        db.add(obj)
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
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = _upsert(db, HospitalSettings, "hospital_id", hospital_id, payload)
    # Re-register scheduler if fsn_schedule_days changed
    from app.scheduler import schedule_fsn_hospital
    hs = db.get(HospitalSettings, hospital_id)
    schedule_fsn_hospital(hospital_id, hs.fsn_schedule_days or 30)
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
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = _upsert(db, StoreSettings, "store_id", store_id, payload)
    # Re-register indent scheduler if indent_duration_days changed
    if payload.indent_duration_days:
        from app.scheduler import schedule_store_indent
        schedule_store_indent(store_id, payload.indent_duration_days)
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
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    return _upsert(db, ItemSettings, "item_id", item_id, payload)


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
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    return _upsert(db, ItemCategorySettings, "category_id", category_id, payload)


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
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    return _upsert(db, ItemGroupSettings, "group_id", group_id, payload)


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
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    return _upsert(db, SupplierSettings, "supplier_id", supplier_id, payload)
