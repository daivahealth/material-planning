from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from typing import Optional
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import csv_import as svc
from app.models.consumption import ConsumptionRecord, ClosingStock, OpenIndent
from app.services.auth import require_master

# All imports are master-only (they mutate data)
router = APIRouter(
    prefix="/api/imports",
    tags=["CSV Imports"],
    dependencies=[Depends(require_master)],
)


@router.post("/consumption")
async def import_consumption(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")
    result = svc.import_consumption(db, file.file)
    return result


@router.delete("/consumption")
def clear_consumption(
    store_id: Optional[int] = Query(None),
    item_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(ConsumptionRecord)
    if store_id:
        q = q.filter(ConsumptionRecord.store_id == store_id)
    if item_id:
        q = q.filter(ConsumptionRecord.item_id == item_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


@router.post("/closing-stock")
async def import_closing_stock(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")
    result = svc.import_closing_stock(db, file.file)
    return result


@router.delete("/closing-stock")
def clear_closing_stock(
    store_id: Optional[int] = Query(None),
    item_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(ClosingStock)
    if store_id:
        q = q.filter(ClosingStock.store_id == store_id)
    if item_id:
        q = q.filter(ClosingStock.item_id == item_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


@router.post("/surge")
async def import_surge(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")
    result = svc.import_surge(db, file.file)
    return result


@router.post("/open-indents")
async def import_open_indent(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")
    result = svc.import_open_indent(db, file.file)
    return result


@router.delete("/open-indents")
def clear_open_indents(
    store_id: Optional[int] = Query(None),
    item_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(OpenIndent)
    if store_id:
        q = q.filter(OpenIndent.store_id == store_id)
    if item_id:
        q = q.filter(OpenIndent.item_id == item_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


@router.post("/item-groups")
async def import_item_groups(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")
    result = svc.import_item_groups(db, file.file)
    return result


@router.post("/item-categories")
async def import_item_categories(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")
    result = svc.import_item_categories(db, file.file)
    return result


@router.post("/items")
async def import_items(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")
    result = svc.import_items(db, file.file)
    return result
