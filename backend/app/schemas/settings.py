from pydantic import BaseModel, model_validator
from typing import Optional
from app.services.formula import validate_formula

FORECAST_METHODS = {"baseline_avg", "weighted_rolling", "trend_adjusted"}


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
    forecast_method: Optional[str] = None
    rolling_recent_weight_factor: Optional[float] = None
    rolling_bucket_days: Optional[int] = None
    trend_min_points: Optional[int] = None
    planning_enabled: Optional[bool] = None

    @model_validator(mode="after")
    def validate_custom_formula(self):
        if self.forecast_method and self.forecast_method not in FORECAST_METHODS:
            raise ValueError("forecast_method must be one of: baseline_avg, weighted_rolling, trend_adjusted")

        if self.rolling_recent_weight_factor is not None and self.rolling_recent_weight_factor < 1.0:
            raise ValueError("rolling_recent_weight_factor must be >= 1.0")

        if self.rolling_bucket_days is not None and self.rolling_bucket_days < 1:
            raise ValueError("rolling_bucket_days must be >= 1")

        if self.trend_min_points is not None and self.trend_min_points < 2:
            raise ValueError("trend_min_points must be >= 2")

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
    planning_enabled: Optional[bool] = None


class StoreSettingsCreate(StoreSettingsBase):
    pass


class StoreSettingsOut(StoreSettingsBase):
    store_id: int

    model_config = {"from_attributes": True}


class ItemSettingsBase(BaseModel):
    indent_duration_days: Optional[int] = None
    pack_size: Optional[int] = None
    safety_stock_pct: Optional[float] = None
    reorder_level: Optional[float] = None
    min_stock: Optional[float] = None
    max_stock: Optional[float] = None
    lookback_days: Optional[int] = None
    planning_enabled: Optional[bool] = None


class ItemSettingsCreate(ItemSettingsBase):
    pass


class ItemSettingsOut(ItemSettingsBase):
    item_id: int

    model_config = {"from_attributes": True}


class ItemCategorySettingsBase(BaseModel):
    indent_duration_days: Optional[int] = None
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
    indent_duration_days: Optional[int] = None
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
