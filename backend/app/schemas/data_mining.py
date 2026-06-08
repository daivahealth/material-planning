from __future__ import annotations
import enum
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, field_validator


class DataTypeEnum(str, enum.Enum):
    consumption = "consumption"
    closing_stock = "closing_stock"
    open_indent = "open_indent"
    item = "item"
    supplier = "supplier"


class DbTypeEnum(str, enum.Enum):
    postgresql = "postgresql"
    mysql = "mysql"
    oracle = "oracle"


class RunStatusEnum(str, enum.Enum):
    never = "never"
    running = "running"
    success = "success"
    error = "error"


# ---------------------------------------------------------------------------
# Required column-mapping keys per data type (for validation)
# ---------------------------------------------------------------------------
_REQUIRED_KEYS: Dict[DataTypeEnum, list[str]] = {
    DataTypeEnum.consumption: ["item_code", "store_code", "date", "quantity"],
    DataTypeEnum.closing_stock: ["item_code", "store_code", "date", "quantity"],
    DataTypeEnum.open_indent: ["item_code", "store_code", "as_of_date", "quantity"],
    DataTypeEnum.item: ["code", "name"],
    DataTypeEnum.supplier: ["code", "name"],
}


def _validate_mapping(data_type: DataTypeEnum, mapping: Dict[str, str]) -> Dict[str, str]:
    required = _REQUIRED_KEYS.get(data_type, [])
    missing = [k for k in required if not mapping.get(k)]
    if missing:
        raise ValueError(
            f"column_mapping missing required keys for {data_type}: {missing}"
        )
    return mapping


# ---------------------------------------------------------------------------
# Config schemas
# ---------------------------------------------------------------------------

class DataMiningConfigBase(BaseModel):
    name: str
    description: Optional[str] = None
    data_type: DataTypeEnum
    db_type: DbTypeEnum
    host: str
    port: int
    database_name: str
    username: str
    query: str
    page_size: int = 1000
    column_mapping: Dict[str, str] = {}
    enabled: bool = True
    schedule_cron: Optional[str] = None

    @field_validator("page_size")
    @classmethod
    def page_size_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("page_size must be >= 0 (0 = no pagination)")
        return v

    @field_validator("port")
    @classmethod
    def port_range(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("port must be between 1 and 65535")
        return v


class DataMiningConfigCreate(DataMiningConfigBase):
    password: str  # plain text; encrypted before storage

    @field_validator("column_mapping")
    @classmethod
    def validate_mapping(cls, v: Dict[str, str], info: Any) -> Dict[str, str]:
        data_type = info.data.get("data_type")
        if data_type:
            return _validate_mapping(data_type, v)
        return v


class DataMiningConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    db_type: Optional[DbTypeEnum] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # re-encrypted if provided
    query: Optional[str] = None
    page_size: Optional[int] = None
    column_mapping: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None
    schedule_cron: Optional[str] = None


class DataMiningConfigOut(DataMiningConfigBase):
    id: int
    last_run_at: Optional[datetime] = None
    last_run_status: RunStatusEnum = RunStatusEnum.never
    last_rows_fetched: Optional[int] = None
    last_rows_inserted: Optional[int] = None
    last_rows_skipped: Optional[int] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Password is never returned
    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Run schemas
# ---------------------------------------------------------------------------

class DataMiningRunOut(BaseModel):
    id: int
    config_id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: RunStatusEnum
    rows_fetched: int
    rows_inserted: int
    rows_skipped: int
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Misc schemas
# ---------------------------------------------------------------------------

class DataMiningTestResult(BaseModel):
    success: bool
    message: str


class DataMiningStatusOut(BaseModel):
    config: DataMiningConfigOut
    latest_run: Optional[DataMiningRunOut] = None
