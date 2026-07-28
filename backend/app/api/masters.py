from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db import get_db
from app.models.hospital import Hospital
from app.models.store import Store
from app.models.item import Item, ItemGroup, ItemCategory, Supplier, ItemSupplier
from app.models.user import User
from app.schemas.masters import (
    HospitalCreate, HospitalUpdate, HospitalOut,
    StoreCreate, StoreUpdate, StoreOut,
    ItemGroupCreate, ItemGroupOut,
    ItemCategoryCreate, ItemCategoryUpdate, ItemCategoryOut,
    ItemCreate, ItemUpdate, ItemOut,
    SupplierCreate, SupplierUpdate, SupplierOut,
    ItemSupplierCreate, ItemSupplierOut,
)
from app.services.auth import get_current_user, require_master
from app.services.access import accessible_store_ids, accessible_hospital_ids
from app.services import audit

router = APIRouter(
    prefix="/api/masters",
    tags=["Masters"],
    dependencies=[Depends(get_current_user)],
)


# ---- Hospitals ----
@router.get("/hospitals", response_model=List[HospitalOut])
def list_hospitals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Hospital)
    allowed = accessible_hospital_ids(db, current_user)
    if allowed is not None:  # scoped role (planner / planner_view)
        if not allowed:
            return []
        q = q.filter(Hospital.id.in_(allowed))
    return q.all()


@router.post("/hospitals", response_model=HospitalOut, status_code=201)
def create_hospital(
    payload: HospitalCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = Hospital(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit.record(db, current_user, "create", "hospital", obj.id,
                 summary=f"Created hospital {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 details=audit.scrub(payload.model_dump()), request=request)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/hospitals/{hospital_id}", response_model=HospitalOut)
def get_hospital(hospital_id: int, db: Session = Depends(get_db)):
    obj = db.get(Hospital, hospital_id)
    if not obj:
        raise HTTPException(404, "Hospital not found")
    return obj


@router.put("/hospitals/{hospital_id}", response_model=HospitalOut)
def update_hospital(
    hospital_id: int,
    payload: HospitalUpdate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(Hospital, hospital_id)
    if not obj:
        raise HTTPException(404, "Hospital not found")
    _data = payload.model_dump(exclude_none=True)
    _before = {k: getattr(obj, k, None) for k in _data}
    for k, v in _data.items():
        setattr(obj, k, v)
    _changes = audit.diff(_before, audit.scrub(_data))
    if _changes:
        audit.record(db, current_user, "update", obj.__tablename__.rstrip('s'), obj.id,
                     summary=f"Updated {obj.__tablename__} {getattr(obj, 'code', None) or obj.id}: "
                             f"{', '.join(sorted(_changes))}",
                     details=_changes, request=request)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/hospitals/{hospital_id}", status_code=204)
def delete_hospital(
    hospital_id: int,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(Hospital, hospital_id)
    if not obj:
        raise HTTPException(404, "Hospital not found")
    audit.record(db, current_user, "delete", obj.__tablename__.rstrip('s'), obj.id,
                 summary=f"Deleted {obj.__tablename__} {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 request=request)
    db.delete(obj)
    db.commit()


# ---- Stores ----
@router.get("/stores", response_model=List[StoreOut])
def list_stores(
    hospital_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Store)
    if hospital_id:
        q = q.filter(Store.hospital_id == hospital_id)
    allowed = accessible_store_ids(db, current_user)
    if allowed is not None:  # scoped role (planner / planner_view)
        if not allowed:
            return []
        q = q.filter(Store.id.in_(allowed))
    return q.all()


@router.post("/stores", response_model=StoreOut, status_code=201)
def create_store(
    payload: StoreCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = Store(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit.record(db, current_user, "create", "store", obj.id,
                 summary=f"Created store {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 details=audit.scrub(payload.model_dump()), request=request)
    db.commit()
    db.refresh(obj)
    from app.scheduler import schedule_store_indent
    from app.services import settings as settings_svc
    interval = settings_svc.resolve(db, 0, obj.id, "indent_duration_days")
    schedule_store_indent(obj.id, int(interval or 30))
    return obj


@router.get("/stores/{store_id}", response_model=StoreOut)
def get_store(store_id: int, db: Session = Depends(get_db)):
    obj = db.get(Store, store_id)
    if not obj:
        raise HTTPException(404, "Store not found")
    return obj


@router.put("/stores/{store_id}", response_model=StoreOut)
def update_store(
    store_id: int,
    payload: StoreUpdate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(Store, store_id)
    if not obj:
        raise HTTPException(404, "Store not found")
    _data = payload.model_dump(exclude_none=True)
    _before = {k: getattr(obj, k, None) for k in _data}
    for k, v in _data.items():
        setattr(obj, k, v)
    _changes = audit.diff(_before, audit.scrub(_data))
    if _changes:
        audit.record(db, current_user, "update", obj.__tablename__.rstrip('s'), obj.id,
                     summary=f"Updated {obj.__tablename__} {getattr(obj, 'code', None) or obj.id}: "
                             f"{', '.join(sorted(_changes))}",
                     details=_changes, request=request)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/stores/{store_id}", status_code=204)
def delete_store(
    store_id: int,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(Store, store_id)
    if not obj:
        raise HTTPException(404, "Store not found")
    audit.record(db, current_user, "delete", obj.__tablename__.rstrip('s'), obj.id,
                 summary=f"Deleted {obj.__tablename__} {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 request=request)
    db.delete(obj)
    db.commit()


# ---- ItemGroups ----
@router.get("/item-groups", response_model=List[ItemGroupOut])
def list_item_groups(db: Session = Depends(get_db)):
    return db.query(ItemGroup).all()


@router.post("/item-groups", response_model=ItemGroupOut, status_code=201)
def create_item_group(
    payload: ItemGroupCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = ItemGroup(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit.record(db, current_user, "create", "item_group", obj.id,
                 summary=f"Created item_group {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 details=audit.scrub(payload.model_dump()), request=request)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/item-groups/{group_id}", status_code=204)
def delete_item_group(
    group_id: int,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(ItemGroup, group_id)
    if not obj:
        raise HTTPException(404, "ItemGroup not found")
    audit.record(db, current_user, "delete", obj.__tablename__.rstrip('s'), obj.id,
                 summary=f"Deleted {obj.__tablename__} {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 request=request)
    db.delete(obj)
    db.commit()


# ---- ItemCategories ----
@router.get("/item-categories", response_model=List[ItemCategoryOut])
def list_item_categories(db: Session = Depends(get_db)):
    return db.query(ItemCategory).all()


@router.post("/item-categories", response_model=ItemCategoryOut, status_code=201)
def create_item_category(
    payload: ItemCategoryCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = ItemCategory(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit.record(db, current_user, "create", "item_category", obj.id,
                 summary=f"Created item_category {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 details=audit.scrub(payload.model_dump()), request=request)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/item-categories/{category_id}", response_model=ItemCategoryOut)
def update_item_category(
    category_id: int,
    payload: ItemCategoryUpdate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(ItemCategory, category_id)
    if not obj:
        raise HTTPException(404, "ItemCategory not found")
    _data = payload.model_dump(exclude_none=True)
    _before = {k: getattr(obj, k, None) for k in _data}
    for k, v in _data.items():
        setattr(obj, k, v)
    _changes = audit.diff(_before, audit.scrub(_data))
    if _changes:
        audit.record(db, current_user, "update", obj.__tablename__.rstrip('s'), obj.id,
                     summary=f"Updated {obj.__tablename__} {getattr(obj, 'code', None) or obj.id}: "
                             f"{', '.join(sorted(_changes))}",
                     details=_changes, request=request)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/item-categories/{category_id}", status_code=204)
def delete_item_category(
    category_id: int,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(ItemCategory, category_id)
    if not obj:
        raise HTTPException(404, "ItemCategory not found")
    audit.record(db, current_user, "delete", obj.__tablename__.rstrip('s'), obj.id,
                 summary=f"Deleted {obj.__tablename__} {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 request=request)
    db.delete(obj)
    db.commit()


# ---- Suppliers ----
@router.get("/suppliers", response_model=List[SupplierOut])
def list_suppliers(db: Session = Depends(get_db)):
    return db.query(Supplier).all()


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(
    payload: SupplierCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = Supplier(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit.record(db, current_user, "create", "supplier", obj.id,
                 summary=f"Created supplier {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 details=audit.scrub(payload.model_dump()), request=request)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(Supplier, supplier_id)
    if not obj:
        raise HTTPException(404, "Supplier not found")
    _data = payload.model_dump(exclude_none=True)
    _before = {k: getattr(obj, k, None) for k in _data}
    for k, v in _data.items():
        setattr(obj, k, v)
    _changes = audit.diff(_before, audit.scrub(_data))
    if _changes:
        audit.record(db, current_user, "update", obj.__tablename__.rstrip('s'), obj.id,
                     summary=f"Updated {obj.__tablename__} {getattr(obj, 'code', None) or obj.id}: "
                             f"{', '.join(sorted(_changes))}",
                     details=_changes, request=request)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/suppliers/{supplier_id}", status_code=204)
def delete_supplier(
    supplier_id: int,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(Supplier, supplier_id)
    if not obj:
        raise HTTPException(404, "Supplier not found")
    audit.record(db, current_user, "delete", obj.__tablename__.rstrip('s'), obj.id,
                 summary=f"Deleted {obj.__tablename__} {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 request=request)
    db.delete(obj)
    db.commit()


# ---- Items ----
@router.get("/items", response_model=List[ItemOut])
def list_items(
    group_id: Optional[int] = None,
    category_id: Optional[int] = None,
    search: Optional[str] = Query(None, description="Filter by name or code (case-insensitive)"),
    limit: int = Query(200, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Item)
    if group_id:
        q = q.filter(Item.group_id == group_id)
    if category_id:
        q = q.filter(Item.category_id == category_id)
    if search:
        pattern = f"%{search}%"
        q = q.filter((Item.name.ilike(pattern)) | (Item.code.ilike(pattern)))
    return q.order_by(Item.id).offset(offset).limit(limit).all()


@router.post("/items", response_model=ItemOut, status_code=201)
def create_item(
    payload: ItemCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = Item(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit.record(db, current_user, "create", "item", obj.id,
                 summary=f"Created item {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 details=audit.scrub(payload.model_dump()), request=request)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    obj = db.get(Item, item_id)
    if not obj:
        raise HTTPException(404, "Item not found")
    return obj


@router.put("/items/{item_id}", response_model=ItemOut)
def update_item(
    item_id: int,
    payload: ItemUpdate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(Item, item_id)
    if not obj:
        raise HTTPException(404, "Item not found")
    _data = payload.model_dump(exclude_none=True)
    _before = {k: getattr(obj, k, None) for k in _data}
    for k, v in _data.items():
        setattr(obj, k, v)
    _changes = audit.diff(_before, audit.scrub(_data))
    if _changes:
        audit.record(db, current_user, "update", obj.__tablename__.rstrip('s'), obj.id,
                     summary=f"Updated {obj.__tablename__} {getattr(obj, 'code', None) or obj.id}: "
                             f"{', '.join(sorted(_changes))}",
                     details=_changes, request=request)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/items/{item_id}", status_code=204)
def delete_item(
    item_id: int,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(Item, item_id)
    if not obj:
        raise HTTPException(404, "Item not found")
    audit.record(db, current_user, "delete", obj.__tablename__.rstrip('s'), obj.id,
                 summary=f"Deleted {obj.__tablename__} {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 request=request)
    db.delete(obj)
    db.commit()


# ---- ItemSuppliers ----
@router.get("/item-suppliers/{item_id}", response_model=List[ItemSupplierOut])
def list_item_suppliers(item_id: int, db: Session = Depends(get_db)):
    return db.query(ItemSupplier).filter(ItemSupplier.item_id == item_id).all()


@router.post("/item-suppliers", response_model=ItemSupplierOut, status_code=201)
def create_item_supplier(
    payload: ItemSupplierCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = ItemSupplier(**payload.model_dump())
    db.add(obj)
    db.flush()
    audit.record(db, current_user, "create", "item_supplier", obj.id,
                 summary=f"Created item_supplier {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 details=audit.scrub(payload.model_dump()), request=request)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/item-suppliers/{id}", status_code=204)
def delete_item_supplier(
    id: int,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(ItemSupplier, id)
    if not obj:
        raise HTTPException(404, "Not found")
    audit.record(db, current_user, "delete", obj.__tablename__.rstrip('s'), obj.id,
                 summary=f"Deleted {obj.__tablename__} {getattr(obj, 'code', None) or getattr(obj, 'name', obj.id)}",
                 request=request)
    db.delete(obj)
    db.commit()
