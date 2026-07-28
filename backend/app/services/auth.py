"""
Authentication and authorisation helpers.

* Password hashing via bcrypt (direct — no passlib).
* JWT creation/verification (python-jose).
* FastAPI dependency factories: get_current_user, require_master.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Password helpers (bcrypt directly — avoids passlib/bcrypt 4.x compat issues)
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def password_age_days(user: User) -> Optional[float]:
    """Days since the password was last set, or None if never recorded."""
    changed = getattr(user, "password_changed_at", None)
    if changed is None:
        return None
    if changed.tzinfo is None:                    # tolerate naive timestamps
        changed = changed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - changed).total_seconds() / 86400.0


def password_expired(user: User) -> bool:
    """True when the rotation period has elapsed. A user with no recorded
    change date is never treated as expired — that would lock out accounts
    created before the column existed."""
    max_age = settings.password_max_age_days
    if max_age <= 0:
        return False
    age = password_age_days(user)
    return age is not None and age >= max_age


def days_until_password_expiry(user: User) -> Optional[int]:
    max_age = settings.password_max_age_days
    age = password_age_days(user)
    if max_age <= 0 or age is None:
        return None
    return int(max_age - age)


def _authenticate(token: str, db: Session) -> User:
    payload = _decode_token(token)
    if payload is None:
        raise _CREDENTIALS_EXC
    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise _CREDENTIALS_EXC
    user: Optional[User] = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXC
    return user


def get_current_user_allow_expired(
    token: str = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Authenticated user WITHOUT the password-rotation check.

    Only for endpoints a user must still reach while their password is expired
    — namely changing that password, and reading their own profile.
    """
    return _authenticate(token, db)


def get_current_user(
    token: str = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    user = _authenticate(token, db)
    # Rotation is enforced server-side, not just in the UI: an expired password
    # may authenticate but may not be used to do anything except change itself.
    if password_expired(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your password has expired. Set a new password to continue.",
            headers={"X-Password-Expired": "true"},
        )
    return user


def require_master(current_user: User = Depends(get_current_user)) -> User:
    """Dependency that only allows users with the `master` role."""
    if str(current_user.role) != UserRole.master.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master role required for this action",
        )
    return current_user


def require_roles(*roles):
    """Dependency factory: allow only the given roles (master is not implicit —
    include it explicitly where wanted)."""
    allowed = {r.value if isinstance(r, UserRole) else str(r) for r in roles}

    def _dep(current_user: User = Depends(get_current_user)) -> User:
        if str(current_user.role) not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your role is not permitted to perform this action",
            )
        return current_user

    return _dep
