from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, model_validator

DB_TYPES = {"postgresql", "mysql", "oracle"}
OUTBOUND_FIELDS = ["item_code", "store_code", "qty", "request_number", "request_type", "inserted_date", "request_status"]


class OutboundSettingBase(BaseModel):
    enabled: Optional[bool] = None
    db_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None                # plaintext in; encrypted at rest, never returned
    target_table: Optional[str] = None
    column_mapping: Optional[dict] = None
    request_status_value: Optional[str] = None
    request_type_value: Optional[str] = None
    schedule_cron: Optional[str] = None
    kafka_brokers: Optional[str] = None
    kafka_topic: Optional[str] = None

    @model_validator(mode="after")
    def _validate(self):
        if self.db_type is not None and self.db_type not in DB_TYPES:
            raise ValueError("db_type must be one of: postgresql, mysql, oracle")
        if self.schedule_cron:
            if len(self.schedule_cron.strip().split()) != 5:
                raise ValueError("schedule_cron must be a 5-field cron expression")
        if self.column_mapping is not None:
            bad = [k for k in self.column_mapping if k not in OUTBOUND_FIELDS]
            if bad:
                raise ValueError(f"column_mapping keys must be from {OUTBOUND_FIELDS}; invalid: {bad}")
        return self


class OutboundSettingUpsert(OutboundSettingBase):
    pass


class OutboundSettingOut(BaseModel):
    id: int
    enabled: bool
    db_type: str
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    has_password: bool = False
    target_table: Optional[str] = None
    column_mapping: dict = {}
    request_status_value: str = "NEW"
    request_type_value: str = "StockIndent"
    schedule_cron: Optional[str] = None
    kafka_brokers: Optional[str] = None
    kafka_topic: Optional[str] = None
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_error: Optional[str] = None

    model_config = {"from_attributes": True}


class OutboundDispatchOut(BaseModel):
    id: int
    store_id: int
    period_start: date
    period_end: Optional[date] = None
    request_number: str
    status: str
    rows_written: int
    error: Optional[str] = None
    created_at: datetime
    published_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ConnectionTestResult(BaseModel):
    success: bool
    error: Optional[str] = None


class PurchaseRequestCreate(BaseModel):
    store_id: int
    period_start: date
    item_ids: list[int]
