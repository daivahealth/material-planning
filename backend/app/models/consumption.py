from sqlalchemy import Column, Integer, Date, Numeric, ForeignKey, String, Index
from sqlalchemy.orm import relationship
from app.db import Base


# Single-column indexes on id/item_id/store_id are deliberately absent on the
# three snapshot tables below: id duplicates the primary key, and item_id /
# store_id are each the leading column of a composite index declared underneath.
# They only added write cost — these tables take millions of rows a day.
class ConsumptionRecord(Base):
    __tablename__ = "consumption_records"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric(20, 4), nullable=False)

    item = relationship("Item", back_populates="consumption_records")
    store = relationship("Store", back_populates="consumption_records")


Index("ix_consumption_item_store_date", ConsumptionRecord.item_id, ConsumptionRecord.store_id, ConsumptionRecord.date)
# Store-first: the batch indent path reads a whole store's window in one query.
# The item-first index above cannot serve a store_id + date range filter.
Index("ix_consumption_store_date_item", ConsumptionRecord.store_id, ConsumptionRecord.date, ConsumptionRecord.item_id)


class ClosingStock(Base):
    __tablename__ = "closing_stocks"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric(20, 4), nullable=False)

    item = relationship("Item", back_populates="closing_stocks")
    store = relationship("Store", back_populates="closing_stocks")


Index("ix_closingstock_item_store_date", ClosingStock.item_id, ClosingStock.store_id, ClosingStock.date)
# Store-first: serves both "which items does this store track" (DISTINCT item_id
# by store) and the latest-per-item lookup the batch path does. Without it those
# fall back to reading every row the store has ever had.
Index("ix_closingstock_store_item_date", ClosingStock.store_id, ClosingStock.item_id, ClosingStock.date)


class OpenIndent(Base):
    """
    Represents pending / in-transit indent quantity for an item at a store.
    The sum of open indents as of a given date is subtracted from the projected
    requirement so that already-ordered stock is not double-counted.
    """
    __tablename__ = "open_indents"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    as_of_date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric(20, 4), nullable=False)
    reference = Column(String(255), nullable=True)   # optional PO / indent ref number

    item = relationship("Item", back_populates="open_indents")
    store = relationship("Store", back_populates="open_indents")


Index("ix_openindent_item_store_date", OpenIndent.item_id, OpenIndent.store_id, OpenIndent.as_of_date)
# Store-first counterpart, for the batch path's per-store snapshot lookup.
Index("ix_openindent_store_item_date", OpenIndent.store_id, OpenIndent.item_id, OpenIndent.as_of_date)
