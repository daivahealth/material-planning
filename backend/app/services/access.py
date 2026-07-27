"""
Location-scoping helpers for planner / planner_view users.

`master` and `viewer` are unscoped: the resolvers return ``None`` for them,
which every caller treats as "no filter — all locations".

`planner` / `planner_view` are scoped to:
    stores of their granted hospitals  ∪  their individually granted stores
A planner with no grants resolves to an empty set (sees nothing) — the secure
default agreed for this feature.
"""
from __future__ import annotations

from typing import Optional, Set

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.access import UserHospitalAccess, UserStoreAccess
from app.models.store import Store
from app.models.user import User, UserRole

# Roles whose store/hospital visibility is restricted by the mapping tables.
SCOPED_ROLES = {UserRole.planner.value, UserRole.planner_view.value}


def is_scoped(user: User) -> bool:
    return str(user.role) in SCOPED_ROLES


def accessible_store_ids(db: Session, user: User) -> Optional[Set[int]]:
    """Set of store ids the user may access, or ``None`` for unscoped roles."""
    if not is_scoped(user):
        return None

    hospital_ids = [
        row.hospital_id
        for row in db.query(UserHospitalAccess.hospital_id)
        .filter(UserHospitalAccess.user_id == user.id)
        .all()
    ]
    store_ids: Set[int] = {
        row.store_id
        for row in db.query(UserStoreAccess.store_id)
        .filter(UserStoreAccess.user_id == user.id)
        .all()
    }
    if hospital_ids:
        store_ids.update(
            row.id
            for row in db.query(Store.id)
            .filter(Store.hospital_id.in_(hospital_ids))
            .all()
        )
    return store_ids


def accessible_hospital_ids(db: Session, user: User) -> Optional[Set[int]]:
    """Hospitals to show a user: granted hospitals plus the hospitals that own
    any individually granted store. ``None`` for unscoped roles."""
    if not is_scoped(user):
        return None

    hospital_ids: Set[int] = {
        row.hospital_id
        for row in db.query(UserHospitalAccess.hospital_id)
        .filter(UserHospitalAccess.user_id == user.id)
        .all()
    }
    granted_store_ids = [
        row.store_id
        for row in db.query(UserStoreAccess.store_id)
        .filter(UserStoreAccess.user_id == user.id)
        .all()
    ]
    if granted_store_ids:
        hospital_ids.update(
            row.hospital_id
            for row in db.query(Store.hospital_id)
            .filter(Store.id.in_(granted_store_ids))
            .all()
        )
    return hospital_ids


def assert_store_access(db: Session, user: User, store_id: int) -> None:
    """Raise 403 if a scoped user may not touch ``store_id``. No-op otherwise."""
    allowed = accessible_store_ids(db, user)
    if allowed is not None and store_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this store.",
        )
