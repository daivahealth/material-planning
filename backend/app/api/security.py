"""
IP allowlist administration (master only).

Every write invalidates the in-memory cache so the filter picks the change up
on the next request, and is recorded in the audit trail.

**Lock-out guard:** a change that would leave an enforcing allowlist not
covering the caller's own address is rejected with 400 unless `force=true` is
passed — otherwise one typo locks every administrator out of the system.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.security import AllowedIP
from app.models.user import User
from app.services import audit, ip_allowlist, throttle
from app.services.auth import require_master

router = APIRouter(prefix="/api/security/allowed-ips", tags=["Security"])

# Separate router: login-throttle administration.
throttle_router = APIRouter(prefix="/api/security/login-throttle", tags=["Security"])


class ThrottleReset(BaseModel):
    username: Optional[str] = None
    ip: Optional[str] = None


@throttle_router.post("/reset")
def reset_login_throttle(
    payload: ThrottleReset,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    """Clear a brute-force lockout.

    Shared-NAT sites can have legitimate users locked out by someone else's
    failed attempts, and the counters are in-process (no way to clear them from
    outside). An already-signed-in master can release a lock here instead of
    waiting out the window or restarting the service.

    With no username/ip, clears **all** lockouts.
    """
    if payload.username or payload.ip:
        throttle.clear(payload.username, payload.ip)
        target = payload.username or payload.ip
    else:
        throttle.reset_all()
        target = "all"
    audit.record(
        db, current_user, "reset", "login_throttle", target,
        summary=f"Cleared login lockout for {target}", request=request,
    )
    db.commit()
    return {"cleared": target}


class AllowedIPBase(BaseModel):
    cidr: str
    description: Optional[str] = None
    enabled: bool = True

    @field_validator("cidr")
    @classmethod
    def valid_cidr(cls, v: str) -> str:
        try:
            return str(ip_allowlist.parse_cidr(v))
        except ValueError as exc:
            raise ValueError(
                f"'{v}' is not a valid IP address or CIDR range (e.g. 10.1.2.3 or 10.1.0.0/16)"
            ) from exc


class AllowedIPCreate(AllowedIPBase):
    pass


class AllowedIPUpdate(BaseModel):
    cidr: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None

    @field_validator("cidr")
    @classmethod
    def valid_cidr(cls, v):
        if v is None:
            return v
        return AllowedIPBase.valid_cidr(v)


class AllowedIPOut(AllowedIPBase):
    id: int
    created_by: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class AllowlistStatus(BaseModel):
    enforcing: bool          # False when no enabled entries exist → all allowed
    active_rules: int
    your_ip: Optional[str] = None
    your_ip_allowed: bool


def _caller_ip(request: Request) -> Optional[str]:
    from app.main import client_ip_for
    return client_ip_for(request)


def _guard_lockout(db: Session, request: Request, force: bool) -> None:
    """Refuse a change that would lock the caller out.

    Reads the pending rules directly from the session (they are flushed, not
    committed) — deliberately **not** through the shared cache, which must never
    be populated from a transaction that may still roll back.
    """
    if force:
        return
    nets = ip_allowlist.networks_from_db(db)
    if nets and not ip_allowlist.covers(nets, _caller_ip(request)):
        raise HTTPException(
            400,
            f"This change would block your own address ({_caller_ip(request)}) and lock you out. "
            f"Add a rule covering it first, or repeat with force=true if you are certain.",
        )


@router.get("/status", response_model=AllowlistStatus)
def status_(
    request: Request,
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    ip = _caller_ip(request)
    allowed, enforcing = ip_allowlist.is_allowed(db, ip)
    return AllowlistStatus(
        enforcing=enforcing,
        active_rules=len(ip_allowlist.get_networks(db)),
        your_ip=ip,
        your_ip_allowed=allowed,
    )


@router.get("", response_model=List[AllowedIPOut])
def list_allowed_ips(_: User = Depends(require_master), db: Session = Depends(get_db)):
    return db.query(AllowedIP).order_by(AllowedIP.id).all()


@router.post("", response_model=AllowedIPOut, status_code=201)
def create_allowed_ip(
    payload: AllowedIPCreate,
    request: Request,
    force: bool = Query(False, description="Apply even if it would lock you out"),
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    if db.query(AllowedIP).filter(AllowedIP.cidr == payload.cidr).first():
        raise HTTPException(400, f"'{payload.cidr}' is already configured")
    obj = AllowedIP(**payload.model_dump(), created_by=current_user.username)
    db.add(obj)
    db.flush()
    _guard_lockout(db, request, force)
    audit.record(
        db, current_user, "create", "allowed_ip", obj.id,
        summary=f"Allowed IP added: {obj.cidr}" + (f" ({obj.description})" if obj.description else ""),
        details={"cidr": obj.cidr, "enabled": obj.enabled, "description": obj.description},
        request=request,
    )
    db.commit()
    db.refresh(obj)
    ip_allowlist.invalidate()
    return obj


@router.put("/{ip_id}", response_model=AllowedIPOut)
def update_allowed_ip(
    ip_id: int,
    payload: AllowedIPUpdate,
    request: Request,
    force: bool = Query(False),
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(AllowedIP, ip_id)
    if not obj:
        raise HTTPException(404, "Allowed IP not found")
    data = payload.model_dump(exclude_none=True)
    before = {k: getattr(obj, k, None) for k in data}
    for k, v in data.items():
        setattr(obj, k, v)
    db.flush()
    _guard_lockout(db, request, force)
    changes = audit.diff(before, data)
    if changes:
        audit.record(
            db, current_user, "update", "allowed_ip", obj.id,
            summary=f"Allowed IP {obj.cidr} updated: {', '.join(sorted(changes))}",
            details=changes, request=request,
        )
    db.commit()
    db.refresh(obj)
    ip_allowlist.invalidate()
    return obj


@router.delete("/{ip_id}", status_code=204)
def delete_allowed_ip(
    ip_id: int,
    request: Request,
    force: bool = Query(False),
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = db.get(AllowedIP, ip_id)
    if not obj:
        raise HTTPException(404, "Allowed IP not found")
    cidr = obj.cidr
    audit.record(
        db, current_user, "delete", "allowed_ip", ip_id,
        summary=f"Allowed IP removed: {cidr}", request=request,
    )
    db.delete(obj)
    db.flush()
    _guard_lockout(db, request, force)
    db.commit()
    ip_allowlist.invalidate()
