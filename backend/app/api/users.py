"""
User management endpoints (master role only).

GET    /api/users           — list all users
POST   /api/users           — create user
PUT    /api/users/{id}      — update user (role / email / is_active)
DELETE /api/users/{id}      — delete user
PUT    /api/users/{id}/password — change password
"""
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User, UserRole
from app.models.access import UserHospitalAccess, UserStoreAccess
from app.schemas.user import PasswordChange, UserCreate, UserOut, UserUpdate
from app.services.access import SCOPED_ROLES
from app.services import audit
from app.services.auth import get_current_user, hash_password, require_master

router = APIRouter(prefix="/api/users", tags=["Users"])


def _load_grants(db: Session, user: User) -> User:
    """Attach hospital_ids / store_ids to the ORM object for UserOut."""
    user.hospital_ids = [
        r.hospital_id for r in db.query(UserHospitalAccess.hospital_id)
        .filter(UserHospitalAccess.user_id == user.id).all()
    ]
    user.store_ids = [
        r.store_id for r in db.query(UserStoreAccess.store_id)
        .filter(UserStoreAccess.user_id == user.id).all()
    ]
    return user


def _sync_grants(db: Session, user: User, hospital_ids, store_ids) -> None:
    """Replace a user's location grants. Non-scoped roles never keep grants.
    Passing None for a list leaves that grant type untouched."""
    if str(user.role) not in SCOPED_ROLES:
        # master / viewer are unscoped — clear any stale grants.
        db.query(UserHospitalAccess).filter(UserHospitalAccess.user_id == user.id).delete()
        db.query(UserStoreAccess).filter(UserStoreAccess.user_id == user.id).delete()
        return
    if hospital_ids is not None:
        db.query(UserHospitalAccess).filter(UserHospitalAccess.user_id == user.id).delete()
        for hid in dict.fromkeys(hospital_ids):
            db.add(UserHospitalAccess(user_id=user.id, hospital_id=hid))
    if store_ids is not None:
        db.query(UserStoreAccess).filter(UserStoreAccess.user_id == user.id).delete()
        for sid in dict.fromkeys(store_ids):
            db.add(UserStoreAccess(user_id=user.id, store_id=sid))


@router.get("", response_model=List[UserOut])
def list_users(
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    return [_load_grants(db, u) for u in db.query(User).order_by(User.id).all()]


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(400, "Username already taken")
    if payload.email and db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "Email already in use")
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role.value,
        password_changed_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()  # assign user.id before writing grants
    _sync_grants(db, user, payload.hospital_ids, payload.store_ids)
    audit.record(
        db, current_user, "create", "user", user.id,
        summary=f"Created user '{user.username}' with role {user.role}",
        details={"role": user.role, "email": user.email,
                 "hospital_ids": payload.hospital_ids, "store_ids": payload.store_ids},
        request=request,
    )
    db.commit()
    db.refresh(user)
    return _load_grants(db, user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    data = payload.model_dump(exclude_none=True)
    # Grants are handled separately — they are not columns on User.
    hospital_ids = data.pop("hospital_ids", None)
    store_ids = data.pop("store_ids", None)
    if "role" in data and hasattr(data["role"], "value"):
        data["role"] = data["role"].value
    before = {k: getattr(user, k, None) for k in data}
    before_grants = {
        "hospital_ids": sorted(r.hospital_id for r in db.query(UserHospitalAccess.hospital_id)
                               .filter(UserHospitalAccess.user_id == user.id).all()),
        "store_ids": sorted(r.store_id for r in db.query(UserStoreAccess.store_id)
                            .filter(UserStoreAccess.user_id == user.id).all()),
    }
    for k, v in data.items():
        setattr(user, k, v)
    db.flush()  # apply role change before grants are (re)synced
    _sync_grants(db, user, hospital_ids, store_ids)
    changes = audit.diff(before, data)
    if hospital_ids is not None and sorted(hospital_ids) != before_grants["hospital_ids"]:
        changes["hospital_ids"] = {"from": before_grants["hospital_ids"], "to": sorted(hospital_ids)}
    if store_ids is not None and sorted(store_ids) != before_grants["store_ids"]:
        changes["store_ids"] = {"from": before_grants["store_ids"], "to": sorted(store_ids)}
    if changes:
        audit.record(
            db, current_user, "update", "user", user.id,
            summary=f"Updated user '{user.username}': {', '.join(sorted(changes))}",
            details=changes, request=request,
        )
    db.commit()
    db.refresh(user)
    return _load_grants(db, user)


@router.post("/{user_id}/unlock", response_model=UserOut)
def unlock_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    """Release an account locked by consecutive failed sign-ins.

    Equivalent to the DB-level release:
        UPDATE users SET failed_login_attempts = 0, locked_at = NULL
         WHERE username = '<user>';
    Also clears any in-memory throttle for that username so the user can retry
    immediately rather than waiting out the rate-limit window.
    """
    from app.services import throttle

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    was_locked = user.locked_at is not None
    user.locked_at = None
    user.failed_login_attempts = 0
    throttle.clear(user.username, None)
    audit.record(
        db, current_user, "unlock", "user", user.id,
        summary=(f"Unlocked account '{user.username}'" if was_locked
                 else f"Reset failed-attempt counter for '{user.username}' (was not locked)"),
        details={"was_locked": was_locked}, request=request,
    )
    db.commit()
    db.refresh(user)
    return _load_grants(db, user)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(400, "Cannot delete your own account")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    audit.record(
        db, current_user, "delete", "user", user.id,
        summary=f"Deleted user '{user.username}' (role {user.role})",
        details={"username": user.username, "role": str(user.role), "email": user.email},
        request=request,
    )
    db.delete(user)
    db.commit()


@router.put("/{user_id}/password", response_model=UserOut)
def change_password(
    user_id: int,
    payload: PasswordChange,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Master can change anyone's password; others can only change their own.
    from app.models.user import UserRole
    if current_user.role != UserRole.master and current_user.id != user_id:
        raise HTTPException(403, "You can only change your own password")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.hashed_password = hash_password(payload.new_password)
    # Reset the rotation clock — the new password is good for a full period.
    user.password_changed_at = datetime.now(timezone.utc)
    audit.record(
        db, current_user, "change_password", "user", user.id,
        summary=(f"Changed own password" if current_user.id == user.id
                 else f"Reset password for user '{user.username}'"),
        request=request,
    )
    db.commit()
    db.refresh(user)
    return user
