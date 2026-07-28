"""
Application audit trail — who did what, when, from where.

Append-only by convention: the app only ever INSERTs here, and there is no API
to update or delete entries. Written in the same transaction as the change it
describes, so an audited action cannot commit without its audit record.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Index
from sqlalchemy.sql import func

from app.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity", "entity_id"),
        Index("ix_audit_actor_time", "actor_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Actor — id/username captured at the time of the action so the record
    # survives the user being renamed or deleted.
    actor_id = Column(Integer, nullable=True, index=True)
    actor_username = Column(String(100), nullable=True)
    actor_role = Column(String(20), nullable=True)
    # What happened: action is a short verb ("create", "update", "delete",
    # "login", "generate_indent", …); entity is the object type.
    action = Column(String(50), nullable=False, index=True)
    entity = Column(String(50), nullable=False)
    entity_id = Column(String(64), nullable=True)
    # Human-readable summary plus optional structured before/after.
    summary = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
