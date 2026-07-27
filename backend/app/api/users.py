"""
User management endpoints (master role only).

GET    /api/users           — list all users
POST   /api/users           — create user
PUT    /api/users/{id}      — update user (role / email / is_active)
DELETE /api/users/{id}      — delete user
PUT    /api/users/{id}/password — change password
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User, UserRole
from app.models.access import UserHospitalAccess, UserStoreAccess
from app.schemas.user import PasswordChange, UserCreate, UserOut, UserUpdate
from app.services.access import SCOPED_ROLES
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
    _: User = Depends(require_master),
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
    )
    db.add(user)
    db.flush()  # assign user.id before writing grants
    _sync_grants(db, user, payload.hospital_ids, payload.store_ids)
    db.commit()
    db.refresh(user)
    return _load_grants(db, user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    _: User = Depends(require_master),
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
    for k, v in data.items():
        setattr(user, k, v)
    db.flush()  # apply role change before grants are (re)synced
    _sync_grants(db, user, hospital_ids, store_ids)
    db.commit()
    db.refresh(user)
    return _load_grants(db, user)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    current_user: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(400, "Cannot delete your own account")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    db.delete(user)
    db.commit()


@router.put("/{user_id}/password", response_model=UserOut)
def change_password(
    user_id: int,
    payload: PasswordChange,
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
    db.commit()
    db.refresh(user)
    return user
