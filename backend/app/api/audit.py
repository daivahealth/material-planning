"""
Audit-trail read API (master-only).

Deliberately read-only: there is no endpoint to modify or delete entries, so
the trail cannot be edited through the application.
"""
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.audit import AuditLog
from app.models.user import User
from app.services.auth import require_master

router = APIRouter(prefix="/api/audit", tags=["Audit"])


class AuditLogOut(BaseModel):
    id: int
    actor_id: Optional[int] = None
    actor_username: Optional[str] = None
    actor_role: Optional[str] = None
    action: str
    entity: str
    entity_id: Optional[str] = None
    summary: Optional[str] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=List[AuditLogOut])
def list_audit_logs(
    actor: Optional[str] = Query(None, description="Filter by actor username"),
    action: Optional[str] = Query(None),
    entity: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if actor:
        q = q.filter(AuditLog.actor_username == actor)
    if action:
        q = q.filter(AuditLog.action == action)
    if entity:
        q = q.filter(AuditLog.entity == entity)
    if entity_id:
        q = q.filter(AuditLog.entity_id == str(entity_id))
    if from_date:
        q = q.filter(AuditLog.created_at >= from_date)
    if to_date:
        # inclusive of the whole to_date day
        q = q.filter(AuditLog.created_at < to_date + timedelta(days=1))
    return q.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
