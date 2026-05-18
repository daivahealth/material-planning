from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FSNOut(BaseModel):
    id: int
    item_id: int
    store_id: int
    classification: str
    avg_daily_consumption: float
    period_days: int
    computed_at: datetime

    model_config = {"from_attributes": True}


class VEDOut(BaseModel):
    id: int
    item_id: int
    system_suggestion: str
    manual_override: Optional[str]
    override_reason: Optional[str]
    effective_class: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class VEDOverrideRequest(BaseModel):
    item_id: int
    ved_class: str
    reason: str
