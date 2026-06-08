from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class IndentGenerateRequest(BaseModel):
    item_id: int
    store_id: int
    as_of: Optional[date] = None


class IndentBatchRequest(BaseModel):
    store_id: int
    as_of: Optional[date] = None


class IndentReportOut(BaseModel):
    id: int
    item_id: int
    store_id: int
    # enriched name/code fields (populated by list endpoint)
    item_code: Optional[str] = None
    item_name: Optional[str] = None
    store_code: Optional[str] = None
    store_name: Optional[str] = None
    hospital_name: Optional[str] = None
    preferred_supplier_code: Optional[str] = None
    preferred_supplier_name: Optional[str] = None
    period_start: date
    period_end: date
    avg_daily_consumption: float
    projected_need: float
    closing_stock_qty: float
    safety_stock_qty: float
    base_indent_qty: float
    surge_indent_qty: float
    open_indent_qty: float
    total_indent_qty: float
    formula_used: Optional[str]
    triggered_by: str
    generated_at: datetime

    model_config = {"from_attributes": True}


class SurgeRecordCreate(BaseModel):
    item_id: int
    store_id: int
    recorded_date: date
    extra_qty: float
    reason: str
    season: Optional[str] = None


class SurgeRecordOut(BaseModel):
    id: int
    item_id: int
    store_id: int
    recorded_date: date
    month: int
    season: str
    reason: str
    extra_qty: float

    model_config = {"from_attributes": True}
