"""
Auth endpoints.

POST /api/auth/login           — OAuth2 password flow → JWT token
GET  /api/auth/me              — return currently logged-in user
POST /api/auth/reset-password  — change own password (requires current password)
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.db import get_db
from app.models.user import User
from app.schemas.user import MyPasswordReset, TokenOut, UserOut
from app.services import audit, throttle
from app.services.auth import (
    create_access_token,
    days_until_password_expiry,
    get_current_user_allow_expired,
    hash_password,
    password_expired,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login", response_model=TokenOut)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    ip = audit.client_ip(request)
    user: User | None = (
        db.query(User).filter(User.username == form.username).first()
    )

    # An administrative release (API unlock, or a DBA running the documented
    # UPDATE) leaves the account clean in the database. Honour that immediately
    # by dropping this username's rate-limit counter, so the release actually
    # lets the user back in instead of leaving them stuck behind the throttle.
    # Only the username key is cleared — the per-IP limit still stands, so a
    # release cannot be used to wipe brute-force protection for a whole host.
    if user is not None and user.locked_at is None and not user.failed_login_attempts:
        throttle.clear(form.username, None)

    # Account locked by consecutive failures — refuse before checking the
    # password. Read live from the DB (never cached) so releasing the lock with
    # a plain SQL UPDATE takes effect on the very next attempt.
    if user is not None and user.locked_at is not None:
        throttle.record_failure(form.username, None)
        audit.record(
            db, user, "login_locked", "auth", user.id,
            summary=f"Login refused for '{user.username}' — account is locked",
            details={"locked_at": str(user.locked_at),
                     "failed_login_attempts": user.failed_login_attempts},
            request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="This account is locked after repeated failed sign-in attempts. "
                   "Contact an administrator to unlock it.",
        )

    # Refuse throttled callers before touching the password hash, so a
    # brute-force attempt costs nothing and reveals nothing.
    wait = throttle.retry_after(form.username, ip)
    if wait:
        audit.record(
            db, None, "login_blocked", "auth", None,
            summary=f"Login attempt refused for '{form.username}' — too many failed attempts",
            details={"retry_after_seconds": wait}, request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Please try again later.",
            headers={"Retry-After": str(wait)},
        )

    if user is None or not user.is_active or not verify_password(form.password, user.hashed_password):
        # Attempts against a REAL account are governed by the durable account
        # lockout below, so they do not burn the per-IP budget — otherwise a
        # shared-NAT site (or an admin's own release) would stay blocked by a
        # rate limit that SQL cannot clear. The per-IP counter is reserved for
        # probing at usernames that do not exist, i.e. spraying.
        locked = throttle.record_failure(form.username, ip if user is None else None)
        # Count consecutive wrong passwords against the account itself and lock
        # it durably at the threshold. Only for a real, active account — we must
        # not create lock state for probes at non-existent usernames.
        account_locked = False
        if user is not None and user.is_active:
            threshold = app_settings.account_lockout_threshold
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if threshold > 0 and user.failed_login_attempts >= threshold and user.locked_at is None:
                user.locked_at = datetime.now(timezone.utc)
                account_locked = True
        # Record the failed attempt (no password material) so brute-force and
        # disabled-account probing are visible in the trail.
        audit.record(
            db, user, "login_failed", "auth", getattr(user, "id", None),
            summary=(f"Failed login for '{form.username}'"
                     + (" — ACCOUNT LOCKED" if account_locked else "")
                     + (" — IP/username throttled" if locked else "")),
            details={"reason": "inactive" if user and not user.is_active else "bad_credentials",
                     "throttled": locked, "account_locked": account_locked,
                     "consecutive_failures": getattr(user, "failed_login_attempts", None)},
            request=request,
        )
        db.commit()
        if account_locked:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="This account is now locked after repeated failed sign-in attempts. "
                       "Contact an administrator to unlock it.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Successful sign-in resets the consecutive-failure counter.
    if user.failed_login_attempts:
        user.failed_login_attempts = 0
    throttle.clear(form.username, ip)
    token = create_access_token(user.id, user.username, str(user.role))
    audit.record(db, user, "login", "auth", user.id,
                 summary=f"Login for '{user.username}'", request=request)
    db.commit()
    return TokenOut(
        access_token=token,
        user=UserOut.model_validate(user),
        password_expired=password_expired(user),
        password_expires_in_days=days_until_password_expiry(user),
    )


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user_allow_expired)):
    return current_user


@router.post("/reset-password", response_model=UserOut)
def reset_password(
    payload: MyPasswordReset,
    request: Request,
    current_user: User = Depends(get_current_user_allow_expired),
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
    current_user.password_changed_at = datetime.now(timezone.utc)
    audit.record(db, current_user, "change_password", "user", current_user.id,
                 summary="Changed own password (self-service)", request=request)
    db.commit()
    db.refresh(current_user)
    return current_user
