from sqlalchemy import Column, Integer, Date, Numeric, ForeignKey, String, Index
from sqlalchemy.orm import relationship
from app.db import Base


class ConsumptionRecord(Base):
    __tablename__ = "consumption_records"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric(20, 4), nullable=False)

    item = relationship("Item", back_populates="consumption_records")
    store = relationship("Store", back_populates="consumption_records")


Index("ix_consumption_item_store_date", ConsumptionRecord.item_id, ConsumptionRecord.store_id, ConsumptionRecord.date)


class ClosingStock(Base):
    __tablename__ = "closing_stocks"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric(20, 4), nullable=False)

    item = relationship("Item", back_populates="closing_stocks")
    store = relationship("Store", back_populates="closing_stocks")


Index("ix_closingstock_item_store_date", ClosingStock.item_id, ClosingStock.store_id, ClosingStock.date)


class OpenIndent(Base):
    """
    Represents pending / in-transit indent quantity for an item at a store.
    The sum of open indents as of a given date is subtracted from the projected
    requirement so that already-ordered stock is not double-counted.
    """
    __tablename__ = "open_indents"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    as_of_date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric(20, 4), nullable=False)
    reference = Column(String(255), nullable=True)   # optional PO / indent ref number

    item = relationship("Item", back_populates="open_indents")
    store = relationship("Store", back_populates="open_indents")


Index("ix_openindent_item_store_date", OpenIndent.item_id, OpenIndent.store_id, OpenIndent.as_of_date)
