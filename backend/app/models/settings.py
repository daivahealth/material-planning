from sqlalchemy import Column, Integer, Float, String, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum
from app.db import Base


class FormulaType(str, enum.Enum):
    standard = "standard"
    custom = "custom"


class HospitalSettings(Base):
    __tablename__ = "hospital_settings"

    hospital_id = Column(Integer, ForeignKey("hospitals.id", ondelete="CASCADE"), primary_key=True)
    lookback_days = Column(Integer, default=90, nullable=False)
    fsn_period_days = Column(Integer, default=365, nullable=False)
    fsn_schedule_days = Column(Integer, default=30, nullable=False)  # how often FSN re-computes
    indent_duration_days = Column(Integer, default=30, nullable=False)
    safety_stock_pct = Column(Float, default=0.10, nullable=False)
    reorder_level = Column(Float, nullable=True)
    min_stock = Column(Float, nullable=True)
    max_stock = Column(Float, nullable=True)
    fsn_fast_threshold = Column(Float, default=1.0, nullable=False)   # avg_daily > this → F
    fsn_slow_threshold = Column(Float, default=0.1, nullable=False)   # avg_daily < this → N
    projection_formula = Column(Enum(FormulaType), default=FormulaType.standard, nullable=False)
    projection_formula_expr = Column(String(500), nullable=True)

    hospital = relationship("Hospital", back_populates="settings")


class StoreSettings(Base):
    __tablename__ = "store_settings"

    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True)
    indent_duration_days = Column(Integer, nullable=True)   # overrides hospital if set
    lookback_days = Column(Integer, nullable=True)
    safety_stock_pct = Column(Float, nullable=True)
    reorder_level = Column(Float, nullable=True)
    min_stock = Column(Float, nullable=True)
    max_stock = Column(Float, nullable=True)

    store = relationship("Store", back_populates="settings")


class ItemSettings(Base):
    __tablename__ = "item_settings"

    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    safety_stock_pct = Column(Float, nullable=True)
    reorder_level = Column(Float, nullable=True)
    min_stock = Column(Float, nullable=True)
    max_stock = Column(Float, nullable=True)
    lookback_days = Column(Integer, nullable=True)

    item = relationship("Item", back_populates="settings")


class ItemCategorySettings(Base):
    __tablename__ = "item_category_settings"

    category_id = Column(Integer, ForeignKey("item_categories.id", ondelete="CASCADE"), primary_key=True)
    safety_stock_pct = Column(Float, nullable=True)
    reorder_level = Column(Float, nullable=True)
    min_stock = Column(Float, nullable=True)
    max_stock = Column(Float, nullable=True)

    category = relationship("ItemCategory", back_populates="settings")


class ItemGroupSettings(Base):
    __tablename__ = "item_group_settings"

    group_id = Column(Integer, ForeignKey("item_groups.id", ondelete="CASCADE"), primary_key=True)
    safety_stock_pct = Column(Float, nullable=True)
    reorder_level = Column(Float, nullable=True)
    min_stock = Column(Float, nullable=True)
    max_stock = Column(Float, nullable=True)

    group = relationship("ItemGroup", back_populates="settings")


class SupplierSettings(Base):
    __tablename__ = "supplier_settings"

    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), primary_key=True)
    lead_time_days = Column(Integer, nullable=True)
    moq = Column(Float, nullable=True)

    supplier = relationship("Supplier", back_populates="settings")
