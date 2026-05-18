import csv
import io
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.indent import IndentReport, TriggerType
from app.models.surge import SurgeRecord, get_season, SeasonType
from app.models.item import Item, ItemGroup, ItemCategory, Supplier, ItemSupplier
from app.models.store import Store
from app.models.hospital import Hospital
from app.models.classification import FSNClassification, VEDClassification
from app.schemas.indent import (
    IndentGenerateRequest, IndentBatchRequest,
    IndentReportOut, SurgeRecordCreate, SurgeRecordOut,
)
from app.services.indent import generate_indent, generate_batch

router = APIRouter(prefix="/api/indents", tags=["Indents"])


@router.post("/generate", response_model=IndentReportOut, status_code=201)
def generate_single(payload: IndentGenerateRequest, db: Session = Depends(get_db)):
    return generate_indent(db, payload.item_id, payload.store_id, payload.as_of, TriggerType.api)


@router.post("/generate-batch", status_code=201)
def generate_batch_endpoint(payload: IndentBatchRequest, db: Session = Depends(get_db)):
    reports, skipped = generate_batch(db, payload.store_id, payload.as_of, TriggerType.api)
    return {"generated": len(reports), "skipped": skipped}


@router.get("/", response_model=List[IndentReportOut])
def list_indents(
    store_id: Optional[int] = None,
    item_id: Optional[int] = None,
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    # Single JOIN — indent_reports + stores + hospitals + items in one query
    q = (
        db.query(
            IndentReport,
            Store.code.label("store_code"),
            Store.name.label("store_name"),
            Hospital.name.label("hospital_name"),
            Item.code.label("item_code"),
            Item.name.label("item_name"),
        )
        .join(Store, Store.id == IndentReport.store_id)
        .join(Hospital, Hospital.id == Store.hospital_id)
        .join(Item, Item.id == IndentReport.item_id)
    )
    if store_id:
        q = q.filter(IndentReport.store_id == store_id)
    if item_id:
        q = q.filter(IndentReport.item_id == item_id)
    if from_date:
        q = q.filter(IndentReport.period_start >= from_date)
    if to_date:
        q = q.filter(IndentReport.period_end <= to_date)

    rows = q.order_by(IndentReport.generated_at.desc()).limit(limit).all()

    result = []
    for row in rows:
        d = IndentReportOut.model_validate(row.IndentReport)
        d.store_code = row.store_code
        d.store_name = row.store_name
        d.hospital_name = row.hospital_name
        d.item_code = row.item_code
        d.item_name = row.item_name
        result.append(d)
    return result


@router.delete("/clear")
def clear_indents(
    store_id: Optional[int] = None,
    item_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(IndentReport)
    if store_id:
        q = q.filter(IndentReport.store_id == store_id)
    if item_id:
        q = q.filter(IndentReport.item_id == item_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


@router.get("/export")
def export_indents(
    store_id: Optional[int] = None,
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    # Subquery: latest FSN computed_at per (item_id, store_id)
    fsn_latest_sq = (
        db.query(
            FSNClassification.item_id,
            FSNClassification.store_id,
            func.max(FSNClassification.computed_at).label("max_at"),
        )
        .group_by(FSNClassification.item_id, FSNClassification.store_id)
        .subquery()
    )

    # Single JOIN across all 9 related tables in one round-trip
    q = (
        db.query(
            IndentReport,
            Store.name.label("store_name"),
            Hospital.name.label("hospital_name"),
            Item.code.label("item_code"),
            Item.name.label("item_name"),
            ItemGroup.name.label("group_name"),
            ItemCategory.name.label("cat_name"),
            Supplier.name.label("supplier_name"),
            FSNClassification.classification.label("fsn_class"),
            VEDClassification.manual_override.label("ved_override"),
            VEDClassification.system_suggestion.label("ved_system"),
        )
        .join(Store, Store.id == IndentReport.store_id)
        .join(Hospital, Hospital.id == Store.hospital_id)
        .join(Item, Item.id == IndentReport.item_id)
        .outerjoin(ItemGroup, ItemGroup.id == Item.group_id)
        .outerjoin(ItemCategory, ItemCategory.id == Item.category_id)
        .outerjoin(
            ItemSupplier,
            and_(ItemSupplier.item_id == IndentReport.item_id, ItemSupplier.is_primary == True),
        )
        .outerjoin(Supplier, Supplier.id == ItemSupplier.supplier_id)
        .outerjoin(
            fsn_latest_sq,
            and_(
                fsn_latest_sq.c.item_id == IndentReport.item_id,
                fsn_latest_sq.c.store_id == IndentReport.store_id,
            ),
        )
        .outerjoin(
            FSNClassification,
            and_(
                FSNClassification.item_id == fsn_latest_sq.c.item_id,
                FSNClassification.store_id == fsn_latest_sq.c.store_id,
                FSNClassification.computed_at == fsn_latest_sq.c.max_at,
            ),
        )
        .outerjoin(VEDClassification, VEDClassification.item_id == IndentReport.item_id)
    )
    if store_id:
        q = q.filter(IndentReport.store_id == store_id)
    if from_date:
        q = q.filter(IndentReport.period_start >= from_date)
    if to_date:
        q = q.filter(IndentReport.period_end <= to_date)

    rows = q.order_by(IndentReport.generated_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "hospital_name", "store_name", "item_code", "item_name",
        "item_group", "item_category", "supplier_name",
        "period_start", "period_end", "avg_daily_consumption",
        "projected_need", "closing_stock", "safety_stock",
        "base_indent_qty", "surge_indent_qty", "total_indent_qty",
        "fsn_class", "ved_class", "formula_used", "triggered_by", "generated_at",
    ])
    for row in rows:
        r = row.IndentReport
        writer.writerow([
            row.hospital_name or "",
            row.store_name or "",
            row.item_code or "",
            row.item_name or "",
            row.group_name or "",
            row.cat_name or "",
            row.supplier_name or "",
            r.period_start, r.period_end,
            round(float(r.avg_daily_consumption), 4),
            round(float(r.projected_need), 4),
            round(float(r.closing_stock_qty), 4),
            round(float(r.safety_stock_qty), 4),
            round(float(r.base_indent_qty), 4),
            round(float(r.surge_indent_qty), 4),
            round(float(r.total_indent_qty), 4),
            row.fsn_class or "",
            row.ved_override or row.ved_system or "",
            r.formula_used or "",
            r.triggered_by,
            r.generated_at.isoformat(),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=indent_report.csv"},
    )


# ---- Surge Records ----
@router.post("/surges", response_model=SurgeRecordOut, status_code=201)
def create_surge(payload: SurgeRecordCreate, db: Session = Depends(get_db)):
    season = None
    if payload.season:
        valid = {s.value for s in SeasonType}
        if payload.season not in valid:
            raise HTTPException(400, f"season must be one of {valid}")
        season = SeasonType(payload.season)
    else:
        season = get_season(payload.recorded_date.month)
    rec = SurgeRecord(
        item_id=payload.item_id,
        store_id=payload.store_id,
        recorded_date=payload.recorded_date,
        month=payload.recorded_date.month,
        season=season,
        reason=payload.reason,
        extra_qty=payload.extra_qty,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/surges", response_model=List[SurgeRecordOut])
def list_surges(
    item_id: Optional[int] = None,
    store_id: Optional[int] = None,
    limit: int = Query(1000, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    q = db.query(SurgeRecord)
    if item_id:
        q = q.filter(SurgeRecord.item_id == item_id)
    if store_id:
        q = q.filter(SurgeRecord.store_id == store_id)
    return q.order_by(SurgeRecord.recorded_date.desc()).limit(limit).all()


@router.delete("/surges/clear")
def clear_surges(
    store_id: Optional[int] = None,
    item_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(SurgeRecord)
    if store_id:
        q = q.filter(SurgeRecord.store_id == store_id)
    if item_id:
        q = q.filter(SurgeRecord.item_id == item_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}
