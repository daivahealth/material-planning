"""
IP allowlist — network-level access restriction.

Semantics (deliberately fail-open when unconfigured):
  * No **enabled** entries  → the filter is inactive and every source IP is allowed.
  * One or more enabled     → only those addresses/ranges may reach the API.

Each entry is a single address (``10.1.2.3``) or a CIDR range
(``10.1.0.0/16``), so a hospital LAN can be allowed in one row.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func

from app.db import Base


class AllowedIP(Base):
    __tablename__ = "allowed_ips"

    id = Column(Integer, primary_key=True, index=True)
    # Single address or CIDR range, validated on write.
    cidr = Column(String(64), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    # Disabled rows are ignored by the filter but kept for history.
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
