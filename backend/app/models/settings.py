from sqlalchemy import Column, Integer, Float, String, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
import enum
from app.db import Base


class FormulaType(str, enum.Enum):
    standard = "standard"
    custom = "custom"


class ForecastMethod(str, enum.Enum):
    baseline_avg = "baseline_avg"
    weighted_rolling = "weighted_rolling"
    trend_adjusted = "trend_adjusted"


class HospitalSettings(Base):
    __tablename__ = "hospital_settings"

    hospital_id = Column(Integer, ForeignKey("hospitals.id", ondelete="CASCADE"), primary_key=True)
    lookback_days = Column(Integer, default=90, nullable=False)
    fsn_period_days = Column(Integer, default=365, nullable=False)
    fsn_schedule_days = Column(Integer, default=30, nullable=False)
    indent_duration_days = Column(Integer, default=30, nullable=False)
    safety_stock_days = Column(Float, default=7.0, nullable=False)
    reorder_level = Column(Float, nullable=True)
    min_stock = Column(Float, nullable=True)
    max_stock = Column(Float, nullable=True)
    fsn_fast_threshold = Column(Float, default=1.0, nullable=False)
    fsn_slow_threshold = Column(Float, default=0.1, nullable=False)
    projection_formula = Column(Enum(FormulaType), default=FormulaType.standard, nullable=False)
    projection_formula_expr = Column(String(500), nullable=True)
    forecast_method = Column(String(50), default=ForecastMethod.baseline_avg.value, nullable=False)
    rolling_window_days = Column(Integer, default=30, nullable=False)  # kept for DB compat
    rolling_recent_weight_factor = Column(Float, default=2.0, nullable=False)
    rolling_bucket_days = Column(Integer, default=1, nullable=False)
    trend_min_points = Column(Integer, default=7, nullable=False)
    planning_enabled = Column(Boolean, default=True, nullable=False)

    hospital = relationship("Hospital", back_populates="settings")


class StoreSettings(Base):
    __tablename__ = "store_settings"

    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True)
    indent_duration_days = Column(Integer, nullable=True)
    lookback_days = Column(Integer, nullable=True)
    # Forecast overrides (store overrides hospital)
    forecast_method = Column(String(50), nullable=True)
    rolling_recent_weight_factor = Column(Float, nullable=True)
    rolling_bucket_days = Column(Integer, nullable=True)
    planning_enabled = Column(Boolean, nullable=True)

    store = relationship("Store", back_populates="settings")


class ItemSettings(Base):
    __tablename__ = "item_settings"

    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    indent_duration_days = Column(Integer, nullable=True)
    pack_size = Column(Integer, nullable=True)
    lead_time_days = Column(Integer, nullable=True)
    safety_stock_days = Column(Float, nullable=True)
    reorder_level = Column(Float, nullable=True)
    min_stock = Column(Float, nullable=True)
    max_stock = Column(Float, nullable=True)
    lookback_days = Column(Integer, nullable=True)
    planning_enabled = Column(Boolean, nullable=True)

    item = relationship("Item", back_populates="settings")


class ItemCategorySettings(Base):
    __tablename__ = "item_category_settings"

    category_id = Column(Integer, ForeignKey("item_categories.id", ondelete="CASCADE"), primary_key=True)
    indent_duration_days = Column(Integer, nullable=True)
    safety_stock_days = Column(Float, nullable=True)
    reorder_level = Column(Float, nullable=True)
    min_stock = Column(Float, nullable=True)
    max_stock = Column(Float, nullable=True)

    category = relationship("ItemCategory", back_populates="settings")


class ItemGroupSettings(Base):
    __tablename__ = "item_group_settings"

    group_id = Column(Integer, ForeignKey("item_groups.id", ondelete="CASCADE"), primary_key=True)
    indent_duration_days = Column(Integer, nullable=True)
    safety_stock_days = Column(Float, nullable=True)
    reorder_level = Column(Float, nullable=True)
    min_stock = Column(Float, nullable=True)
    max_stock = Column(Float, nullable=True)

    group = relationship("ItemGroup", back_populates="settings")


class ItemStoreSettings(Base):
    """Per-(item, store) overrides — highest priority in the settings hierarchy."""
    __tablename__ = "item_store_settings"

    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True)
    indent_duration_days = Column(Integer, nullable=True)
    safety_stock_days = Column(Float, nullable=True)
    reorder_level = Column(Float, nullable=True)
    min_stock = Column(Float, nullable=True)
    max_stock = Column(Float, nullable=True)


class SupplierSettings(Base):
    __tablename__ = "supplier_settings"

    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), primary_key=True)
    lead_time_days = Column(Integer, nullable=True)
    moq = Column(Float, nullable=True)

    supplier = relationship("Supplier", back_populates="settings")
