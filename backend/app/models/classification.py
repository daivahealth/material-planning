from sqlalchemy import Column, Integer, Numeric, String, DateTime, ForeignKey, Enum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db import Base


class FSNClass(str, enum.Enum):
    F = "F"
    S = "S"
    N = "N"


class VEDClass(str, enum.Enum):
    V = "V"
    E = "E"
    D = "D"


class FSNClassification(Base):
    __tablename__ = "fsn_classifications"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    classification = Column(Enum(FSNClass), nullable=False)
    avg_daily_consumption = Column(Numeric(12, 4), nullable=False, default=0)
    period_days = Column(Integer, nullable=False)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    item = relationship("Item", back_populates="fsn_classifications")
    store = relationship("Store", back_populates="fsn_classifications")


Index("ix_fsn_item_store", FSNClassification.item_id, FSNClassification.store_id)


class VEDClassification(Base):
    __tablename__ = "ved_classifications"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    system_suggestion = Column(Enum(VEDClass), nullable=False, default=VEDClass.D)
    manual_override = Column(Enum(VEDClass), nullable=True)
    override_reason = Column(String(500), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    item = relationship("Item", back_populates="ved_classification")
