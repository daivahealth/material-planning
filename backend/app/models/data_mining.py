import enum
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, JSON,
    ForeignKey, Enum, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class DataType(str, enum.Enum):
    consumption = "consumption"
    closing_stock = "closing_stock"
    open_indent = "open_indent"
    item = "item"
    supplier = "supplier"


class DbType(str, enum.Enum):
    postgresql = "postgresql"
    mysql = "mysql"
    oracle = "oracle"


class RunStatus(str, enum.Enum):
    never = "never"
    running = "running"
    success = "success"
    error = "error"


class DataMiningConfig(Base):
    __tablename__ = "data_mining_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Target data type
    data_type = Column(Enum(DataType), nullable=False)

    # Source DB connection
    db_type = Column(Enum(DbType), nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    database_name = Column(String(255), nullable=False)
    username = Column(String(255), nullable=False)
    encrypted_password = Column(Text, nullable=False)

    # Query config
    query = Column(Text, nullable=False)
    # 0 = no pagination; >0 = rows per page
    page_size = Column(Integer, nullable=False, default=1000)
    # JSON: {"item_code": "SRC_COL_NAME", "store_code": "STORE_ID", ...}
    column_mapping = Column(JSON, nullable=False, default=dict)

    # Scheduling
    enabled = Column(Boolean, nullable=False, default=True)
    schedule_cron = Column(String(100), nullable=True)  # e.g. "0 2 * * *"

    # Last-run summary (denormalised for fast status display)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(
        Enum(RunStatus), nullable=False, default=RunStatus.never
    )
    last_rows_fetched = Column(Integer, nullable=True)
    last_rows_inserted = Column(Integer, nullable=True)
    last_rows_skipped = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    runs = relationship(
        "DataMiningRun",
        back_populates="config",
        cascade="all, delete-orphan",
        order_by="DataMiningRun.started_at.desc()",
    )


class DataMiningRun(Base):
    __tablename__ = "data_mining_runs"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(
        Integer,
        ForeignKey("data_mining_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(RunStatus), nullable=False, default=RunStatus.running)
    rows_fetched = Column(Integer, nullable=False, default=0)
    rows_inserted = Column(Integer, nullable=False, default=0)
    rows_skipped = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)

    config = relationship("DataMiningConfig", back_populates="runs")


Index(
    "ix_dm_run_config_started",
    DataMiningRun.config_id,
    DataMiningRun.started_at,
)
