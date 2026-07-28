import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db import Base


class UserRole(str, enum.Enum):
    master = "master"            # full access
    viewer = "viewer"            # read-only across all screens
    planner = "planner"          # Indent / Purchase Requisition / Consumption + generate + create PR
    planner_view = "planner_view"  # read-only on those same 3 screens


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    # Stored as plain text (not a DB enum) so new roles need no type migration.
    role = Column(String(20), nullable=False, default=UserRole.viewer.value)
    is_active = Column(Boolean, nullable=False, default=True)
    # Account lockout after consecutive wrong passwords. Persisted (not cached)
    # so the state survives restarts AND so a DBA can release a lock with a
    # plain UPDATE when every administrator is locked out:
    #   UPDATE users SET failed_login_attempts = 0, locked_at = NULL
    #    WHERE username = '<user>';
    failed_login_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    # NULL = not locked. Set when the consecutive-failure threshold is reached;
    # cleared on a successful login or an explicit unlock.
    locked_at = Column(DateTime(timezone=True), nullable=True)
    # When the password was last set — drives the rotation policy
    # (PASSWORD_MAX_AGE_DAYS). Updated on create, self-reset and admin reset.
    password_changed_at = Column(DateTime(timezone=True), nullable=True,
                                 server_default=func.now())
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
