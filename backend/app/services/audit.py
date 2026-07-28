"""
Audit-trail helper.

`record(...)` adds an AuditLog row to the caller's session **without
committing** — so it lands in the same transaction as the change it describes
and can never be committed independently of it.

Auditing must never break a business operation: any failure to build the record
is swallowed and logged rather than raised.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User

log = logging.getLogger("audit")


def client_ip(request: Optional[Request]) -> Optional[str]:
    """Best-effort client IP, honouring a proxy's X-Forwarded-For first hop."""
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return getattr(getattr(request, "client", None), "host", None)


def record(
    db: Session,
    actor: Optional[User],
    action: str,
    entity: str,
    entity_id: object = None,
    summary: Optional[str] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """Queue an audit entry on this session (caller commits)."""
    try:
        db.add(AuditLog(
            actor_id=getattr(actor, "id", None),
            actor_username=getattr(actor, "username", None),
            actor_role=str(getattr(actor, "role", "")) or None,
            action=action,
            entity=entity,
            entity_id=None if entity_id is None else str(entity_id)[:64],
            summary=summary,
            details=details,
            ip_address=client_ip(request),
        ))
    except Exception as exc:  # never break the audited operation
        log.warning("failed to record audit entry %s/%s: %s", action, entity, exc)


def diff(before: dict, after: dict) -> dict:
    """{field: {"from": x, "to": y}} for changed fields — the 'what changed'."""
    out = {}
    for k, new in after.items():
        old = before.get(k)
        if old != new:
            out[k] = {"from": _safe(old), "to": _safe(new)}
    return out


def _safe(v):
    """JSON-safe scalar; never let a credential field into the audit payload."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


# Field names whose values must never be written to the audit trail.
REDACT = {"password", "new_password", "current_password", "hashed_password",
          "encrypted_password", "jwt_secret_key", "mining_secret_key"}


def scrub(data: dict) -> dict:
    """Copy of `data` with secret-bearing fields masked."""
    return {k: ("***" if k in REDACT else _safe(v)) for k, v in (data or {}).items()}
