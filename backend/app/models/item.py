from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Numeric
from sqlalchemy.orm import relationship
from app.db import Base


class ItemGroup(Base):
    __tablename__ = "item_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)

    items = relationship("Item", back_populates="group")
    settings = relationship("ItemGroupSettings", back_populates="group", uselist=False)


class ItemCategory(Base):
    __tablename__ = "item_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    is_vital = Column(Boolean, default=False, nullable=False)   # used for VED system suggestion

    items = relationship("Item", back_populates="category")
    settings = relationship("ItemCategorySettings", back_populates="category", uselist=False)


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True)
    lead_time_days = Column(Integer, default=7, nullable=False)

    item_suppliers = relationship("ItemSupplier", back_populates="supplier")
    settings = relationship("SupplierSettings", back_populates="supplier", uselist=False)


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("item_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("item_categories.id", ondelete="SET NULL"), nullable=True, index=True)
    preferred_supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True)
    unit = Column(String(50), nullable=False, default="Nos")

    group = relationship("ItemGroup", back_populates="items")
    category = relationship("ItemCategory", back_populates="items")
    preferred_supplier = relationship("Supplier", foreign_keys=[preferred_supplier_id])
    item_suppliers = relationship("ItemSupplier", back_populates="item", cascade="all, delete-orphan")
    settings = relationship("ItemSettings", back_populates="item", uselist=False)
    consumption_records = relationship("ConsumptionRecord", back_populates="item")
    closing_stocks = relationship("ClosingStock", back_populates="item")
    open_indents = relationship("OpenIndent", back_populates="item")
    indent_reports = relationship("IndentReport", back_populates="item")
    surge_records = relationship("SurgeRecord", back_populates="item")
    fsn_classifications = relationship("FSNClassification", back_populates="item")
    ved_classification = relationship("VEDClassification", back_populates="item", uselist=False)


class ItemSupplier(Base):
    __tablename__ = "item_suppliers"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    is_primary = Column(Boolean, default=False, nullable=False)
    moq = Column(Numeric(12, 4), nullable=True)  # minimum order quantity

    item = relationship("Item", back_populates="item_suppliers")
    supplier = relationship("Supplier", back_populates="item_suppliers")
