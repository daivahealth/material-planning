from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db import get_db
from app.models.classification import FSNClassification, VEDClassification, VEDClass
from app.models.store import Store
from app.schemas.classification import FSNOut, VEDOut, VEDOverrideRequest
from app.services import fsn as fsn_svc, ved as ved_svc

router = APIRouter(prefix="/api/classification", tags=["Classification"])


@router.post("/fsn/run")
def run_fsn(hospital_id: int, db: Session = Depends(get_db)):
    result = fsn_svc.compute_fsn_for_hospital(db, hospital_id)
    return result


@router.get("/fsn", response_model=List[FSNOut])
def list_fsn(
    hospital_id: Optional[int] = None,
    store_id: Optional[int] = None,
    classification: Optional[str] = None,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(FSNClassification)
    if hospital_id:
        store_ids = db.query(Store.id).filter(Store.hospital_id == hospital_id).subquery()
        q = q.filter(FSNClassification.store_id.in_(store_ids))
    if store_id:
        q = q.filter(FSNClassification.store_id == store_id)
    if classification:
        q = q.filter(FSNClassification.classification == classification)
    return q.offset(offset).limit(limit).all()


@router.post("/ved/run")
def run_ved(db: Session = Depends(get_db)):
    return ved_svc.compute_ved_for_all(db)


@router.get("/ved", response_model=List[VEDOut])
def list_ved(db: Session = Depends(get_db)):
    records = db.query(VEDClassification).all()
    result = []
    for r in records:
        result.append(VEDOut(
            id=r.id,
            item_id=r.item_id,
            system_suggestion=r.system_suggestion,
            manual_override=r.manual_override,
            override_reason=r.override_reason,
            effective_class=ved_svc.effective_ved(r),
            updated_at=r.updated_at,
        ))
    return result


@router.put("/ved/override")
def set_ved_override(payload: VEDOverrideRequest, db: Session = Depends(get_db)):
    valid = {c.value for c in VEDClass}
    if payload.ved_class not in valid:
        raise HTTPException(400, f"ved_class must be one of {valid}")
    record = ved_svc.set_manual_override(db, payload.item_id, VEDClass(payload.ved_class), payload.reason)
    return VEDOut(
        id=record.id,
        item_id=record.item_id,
        system_suggestion=record.system_suggestion,
        manual_override=record.manual_override,
        override_reason=record.override_reason,
        effective_class=ved_svc.effective_ved(record),
        updated_at=record.updated_at,
    )
