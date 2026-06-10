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
from app.models.user import User
from app.schemas.user import PasswordChange, UserCreate, UserOut, UserUpdate
from app.services.auth import get_current_user, hash_password, require_master

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("", response_model=List[UserOut])
def list_users(
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    return db.query(User).order_by(User.id).all()


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
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user


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
