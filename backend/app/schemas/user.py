import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator
from app.models.user import UserRole

# ---------------------------------------------------------------------------
# Shared password-policy helper
# ---------------------------------------------------------------------------
_SPECIAL_RE = re.compile(r'[^a-zA-Z0-9]')


def _validate_password_policy(v: str) -> str:
    """
    Enforce password policy:
      - at least 8 characters
      - at least one uppercase letter  (A-Z)
      - at least one digit             (0-9)
      - at least one special character (anything that is not a-z, A-Z, 0-9)
    Returns the unchanged value on success; raises ValueError on failure.
    """
    errors: list[str] = []
    if len(v) < 8:
        errors.append("at least 8 characters")
    if not re.search(r'[A-Z]', v):
        errors.append("at least one uppercase letter")
    if not re.search(r'[0-9]', v):
        errors.append("at least one number")
    if not _SPECIAL_RE.search(v):
        errors.append("at least one special character")
    if errors:
        raise ValueError("Password must contain: " + ", ".join(errors))
    return v


class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    password: str
    role: UserRole = UserRole.viewer

    @field_validator("username")
    @classmethod
    def username_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("username must not be empty")
        return v

    @field_validator("password")
    @classmethod
    def password_policy(cls, v: str) -> str:
        return _validate_password_policy(v)


class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class PasswordChange(BaseModel):
    """Used by master to forcefully set any user's password."""
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_policy(cls, v: str) -> str:
        return _validate_password_policy(v)


class MyPasswordReset(BaseModel):
    """Used by the currently-logged-in user to change their own password."""
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_policy(cls, v: str) -> str:
        return _validate_password_policy(v)


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
