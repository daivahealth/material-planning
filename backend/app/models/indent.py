from sqlalchemy import Column, Integer, Date, Numeric, String, DateTime, ForeignKey, Enum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db import Base


class TriggerType(str, enum.Enum):
    scheduler = "scheduler"
    manual = "manual"
    api = "api"


class IndentReport(Base):
    __tablename__ = "indent_reports"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    avg_daily_consumption = Column(Numeric(12, 4), nullable=False)
    projected_need = Column(Numeric(12, 4), nullable=False)
    closing_stock_qty = Column(Numeric(12, 4), nullable=False, default=0)
    safety_stock_qty = Column(Numeric(12, 4), nullable=False, default=0)
    base_indent_qty = Column(Numeric(12, 4), nullable=False, default=0)
    surge_indent_qty = Column(Numeric(12, 4), nullable=False, default=0)
    open_indent_qty = Column(Numeric(12, 4), nullable=False, default=0)
    total_indent_qty = Column(Numeric(12, 4), nullable=False, default=0)
    formula_used = Column(String(500), nullable=True)
    triggered_by = Column(Enum(TriggerType), default=TriggerType.api, nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    item = relationship("Item", back_populates="indent_reports")
    store = relationship("Store", back_populates="indent_reports")


Index("ix_indentreport_store_item_gen", IndentReport.store_id, IndentReport.item_id, IndentReport.generated_at)
