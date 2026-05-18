from pydantic import BaseModel, model_validator
from typing import Optional
from app.services.formula import validate_formula


class HospitalSettingsBase(BaseModel):
    lookback_days: Optional[int] = None
    fsn_period_days: Optional[int] = None
    fsn_schedule_days: Optional[int] = None
    indent_duration_days: Optional[int] = None
    safety_stock_pct: Optional[float] = None
    reorder_level: Optional[float] = None
    min_stock: Optional[float] = None
    max_stock: Optional[float] = None
    fsn_fast_threshold: Optional[float] = None
    fsn_slow_threshold: Optional[float] = None
    projection_formula: Optional[str] = None
    projection_formula_expr: Optional[str] = None

    @model_validator(mode="after")
    def validate_custom_formula(self):
        if self.projection_formula == "custom":
            if not self.projection_formula_expr:
                raise ValueError("projection_formula_expr is required when projection_formula is 'custom'")
            ok, err = validate_formula(self.projection_formula_expr)
            if not ok:
                raise ValueError(f"Invalid projection_formula_expr: {err}")
        return self


class HospitalSettingsCreate(HospitalSettingsBase):
    pass


class HospitalSettingsOut(HospitalSettingsBase):
    hospital_id: int

    model_config = {"from_attributes": True}


class StoreSettingsBase(BaseModel):
    indent_duration_days: Optional[int] = None
    lookback_days: Optional[int] = None
    safety_stock_pct: Optional[float] = None
    reorder_level: Optional[float] = None
    min_stock: Optional[float] = None
    max_stock: Optional[float] = None


class StoreSettingsCreate(StoreSettingsBase):
    pass


class StoreSettingsOut(StoreSettingsBase):
    store_id: int

    model_config = {"from_attributes": True}


class ItemSettingsBase(BaseModel):
    safety_stock_pct: Optional[float] = None
    reorder_level: Optional[float] = None
    min_stock: Optional[float] = None
    max_stock: Optional[float] = None
    lookback_days: Optional[int] = None


class ItemSettingsCreate(ItemSettingsBase):
    pass


class ItemSettingsOut(ItemSettingsBase):
    item_id: int

    model_config = {"from_attributes": True}


class ItemCategorySettingsBase(BaseModel):
    safety_stock_pct: Optional[float] = None
    reorder_level: Optional[float] = None
    min_stock: Optional[float] = None
    max_stock: Optional[float] = None


class ItemCategorySettingsCreate(ItemCategorySettingsBase):
    pass


class ItemCategorySettingsOut(ItemCategorySettingsBase):
    category_id: int

    model_config = {"from_attributes": True}


class ItemGroupSettingsBase(BaseModel):
    safety_stock_pct: Optional[float] = None
    reorder_level: Optional[float] = None
    min_stock: Optional[float] = None
    max_stock: Optional[float] = None


class ItemGroupSettingsCreate(ItemGroupSettingsBase):
    pass


class ItemGroupSettingsOut(ItemGroupSettingsBase):
    group_id: int

    model_config = {"from_attributes": True}


class SupplierSettingsBase(BaseModel):
    lead_time_days: Optional[int] = None
    moq: Optional[float] = None


class SupplierSettingsCreate(SupplierSettingsBase):
    pass


class SupplierSettingsOut(SupplierSettingsBase):
    supplier_id: int

    model_config = {"from_attributes": True}


class ResolvedSettings(BaseModel):
    item_id: int
    store_id: int
    settings: dict
