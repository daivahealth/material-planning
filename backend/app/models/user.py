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
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
