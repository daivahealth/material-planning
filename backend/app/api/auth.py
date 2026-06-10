"""
Auth endpoints.

POST /api/auth/login           — OAuth2 password flow → JWT token
GET  /api/auth/me              — return currently logged-in user
POST /api/auth/reset-password  — change own password (requires current password)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.schemas.user import MyPasswordReset, TokenOut, UserOut
from app.services.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login", response_model=TokenOut)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user: User | None = (
        db.query(User).filter(User.username == form.username).first()
    )
    if user is None or not user.is_active or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user.id, user.username, user.role.value)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/reset-password", response_model=UserOut)
def reset_password(
    payload: MyPasswordReset,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Allow any authenticated user to change their own password.
    Requires the correct current password as a security check.
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    db.refresh(current_user)
    return current_user
