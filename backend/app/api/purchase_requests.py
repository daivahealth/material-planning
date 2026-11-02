"""Manual Purchase Request creation from generated indent lines."""
import logging
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from app.db import get_db
from app.models.indent import IndentReport
from app.models.item import Item, Supplier
from app.models.store import Store
from app.models.hospital import Hospital
from app.models.settings import StoreSettings
from app.models.user import User, UserRole
from app.schemas.indent import IndentReportOut
from app.schemas.outbound import PurchaseRequestCreate
from app.services.auth import get_current_user, require_roles
from app.services.access import assert_store_access
from app.services import audit
from app.services.outbound import create_purchase_request

log = logging.getLogger("outbound")

router = APIRouter(
    prefix="/api/purchase-requests",
    tags=["Purchase Requests"],
    dependencies=[Depends(get_current_user)],
)


def _store_is_pr(db: Session, store_id: int) -> bool:
    ss = db.get(StoreSettings, store_id)
    rt = ss.request_type if ss and ss.request_type else "stock_indent"
    return rt == "purchase_request"


class CandidatePeriodOut(BaseModel):
    period_start: date
    period_end: date
    line_count: int          # eligible lines only (positive qty, not PR-initiated)
    is_current: bool         # the store's newest generated period


@router.get("/periods", response_model=List[CandidatePeriodOut])
def list_candidate_periods(
    store_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Periods that have indent lines for a store, newest first.

    Populates the Period selector without pulling every period's lines down.
    ``/candidates`` defaults to the newest period, so anything flagged
    ``is_current = false`` is a superseded plan — its figures were calculated
    from the stock and open-indent data of the day it was generated.
    """
    assert_store_access(db, current_user, store_id)
    rows = (
        db.query(
            IndentReport.period_start,
            func.max(IndentReport.period_end).label("period_end"),
            func.count(IndentReport.id).filter(
                IndentReport.total_indent_qty > 0,
                IndentReport.pr_initiated.is_(False),
            ).label("line_count"),
        )
        .filter(IndentReport.store_id == store_id)
        .group_by(IndentReport.period_start)
        .order_by(IndentReport.period_start.desc())
        .all()
    )
    return [
        CandidatePeriodOut(
            period_start=r.period_start,
            period_end=r.period_end,
            line_count=r.line_count or 0,
            is_current=(i == 0),
        )
        for i, r in enumerate(rows)
    ]


@router.get("/candidates", response_model=List[IndentReportOut])
def list_candidates(
    store_id: int,
    period_start: Optional[date] = Query(None),
    supplier_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Indent lines eligible for a Purchase Request: positive qty, not yet
    PR-initiated, for a store configured as purchase_request."""
    assert_store_access(db, current_user, store_id)
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(404, "Store not found")
    if not _store_is_pr(db, store_id):
        raise HTTPException(
            400,
            "Store is not configured for Purchase Request. "
            "Set request_type = purchase_request in Store settings.",
        )

    PrefSupplier = aliased(Supplier)
    q = (
        db.query(
            IndentReport,
            Store.code.label("store_code"),
            Store.name.label("store_name"),
            Hospital.name.label("hospital_name"),
            Item.code.label("item_code"),
            Item.name.label("item_name"),
            PrefSupplier.code.label("preferred_supplier_code"),
            PrefSupplier.name.label("preferred_supplier_name"),
        )
        .join(Store, Store.id == IndentReport.store_id)
        .join(Hospital, Hospital.id == Store.hospital_id)
        .join(Item, Item.id == IndentReport.item_id)
        .outerjoin(PrefSupplier, PrefSupplier.id == Item.preferred_supplier_id)
        .filter(
            IndentReport.store_id == store_id,
            IndentReport.total_indent_qty > 0,
            IndentReport.pr_initiated.is_(False),
        )
    )
    # Default to the store's CURRENT plan, not every period ever generated.
    #
    # Regeneration replaces only the period it generates, so a run on a new date
    # leaves earlier periods in place. Returning all of them meant an item
    # restocked above its target still showed a positive quantity from a
    # superseded plan, and with ~1.5-2.5k lines per period the 5000-row cap was
    # being hit by stale rows. An explicit period_start still wins, so an older
    # period can be inspected deliberately via /periods.
    if period_start:
        q = q.filter(IndentReport.period_start == period_start)
    else:
        latest = (
            db.query(func.max(IndentReport.period_start))
            .filter(IndentReport.store_id == store_id)
            .scalar()
        )
        if latest is None:
            return []
        q = q.filter(IndentReport.period_start == latest)
    if supplier_id:
        q = q.filter(Item.preferred_supplier_id == supplier_id)

    rows = q.order_by(IndentReport.period_start.desc(), Item.code.asc()).limit(5000).all()
    result = []
    for row in rows:
        d = IndentReportOut.model_validate(row.IndentReport)
        d.store_code = row.store_code
        d.store_name = row.store_name
        d.hospital_name = row.hospital_name
        d.item_code = row.item_code
        d.item_name = row.item_name
        d.preferred_supplier_code = row.preferred_supplier_code
        d.preferred_supplier_name = row.preferred_supplier_name
        result.append(d)
    return result


@router.post("")
def create_pr(
    payload: PurchaseRequestCreate,
    request: Request,
    current_user: User = Depends(require_roles(UserRole.master, UserRole.planner)),
    db: Session = Depends(get_db),
):
    assert_store_access(db, current_user, payload.store_id)
    try:
        result = create_purchase_request(
            db, payload.store_id, payload.period_start, payload.item_ids
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    # Audited after the fact: create_purchase_request commits internally, so the
    # trail records the outcome (request number) rather than the intent.
    audit.record(
        db, current_user, "create", "purchase_request", result.get("request_number"),
        summary=(f"Raised purchase request {result.get('request_number')} for store "
                 f"{payload.store_id} ({result.get('rows')} line(s))"),
        details={"store_id": payload.store_id, "period_start": str(payload.period_start),
                 "rows": result.get("rows"), "item_ids": result.get("item_ids")},
        request=request,
    )
    db.commit()
    return result
