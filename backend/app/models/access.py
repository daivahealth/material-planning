"""
User → location access mappings.

Scoping applies ONLY to the `planner` / `planner_view` roles: they can access
just the hospitals and stores granted here. `master` / `viewer` are never
filtered (they implicitly see everything).

Two grant types, unioned when resolving a planner's accessible stores:
  * hospital grant  → all current AND future stores of that hospital
  * store grant     → one specific store (finer exceptions)
"""
from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from app.db import Base


class UserHospitalAccess(Base):
    __tablename__ = "user_hospital_access"
    __table_args__ = (
        UniqueConstraint("user_id", "hospital_id", name="uq_user_hospital"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)


class UserStoreAccess(Base):
    __tablename__ = "user_store_access"
    __table_args__ = (
        UniqueConstraint("user_id", "store_id", name="uq_user_store"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
