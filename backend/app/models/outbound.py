"""
Outbound dispatch models.

Pipeline: a scheduled job generates indents for stores whose request_type is
`stock_indent`, writes the indent lines to an external "outbound" table
(connection configured globally in OutboundSetting), stamps a per-store,
per-day request number, and publishes that number to Kafka via a
transactional outbox.

Tables:
  outbound_settings        — singleton global config (target DB + Kafka topic)
  store_request_sequences  — per-(store, day) counter for request numbers
  outbound_dispatches      — one row per (store, period); idempotency + status
  outbox_events            — durable Kafka publish queue (transactional outbox)
"""
import enum

from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Boolean, JSON,
    Enum, ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.sql import func

from app.db import Base
from app.models.data_mining import DbType  # reuse postgresql|mysql|oracle


class DispatchStatus(str, enum.Enum):
    pending = "pending"      # request number allocated, not yet written
    inserted = "inserted"    # rows written to the external outbound table
    published = "published"  # request number published to Kafka
    failed = "failed"        # a step errored; will be retried next run


class OutboxStatus(str, enum.Enum):
    unpublished = "unpublished"
    published = "published"
    failed = "failed"


class OutboundSetting(Base):
    """Global (singleton) configuration for the outbound pipeline.

    A single enabled row drives the pipeline. The target table lives in an
    external database (like data-mining sources); the password is Fernet
    encrypted at rest with MINING_SECRET_KEY.
    """
    __tablename__ = "outbound_settings"

    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Boolean, nullable=False, default=False)

    # External target database connection
    db_type = Column(Enum(DbType), nullable=False, default=DbType.postgresql)
    host = Column(String(255), nullable=True)
    port = Column(Integer, nullable=True)
    database_name = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)
    encrypted_password = Column(Text, nullable=True)

    # Target table + field→column mapping. Internal fields:
    #   item_code, store_code, qty, request_number, inserted_date, request_status
    target_table = Column(String(255), nullable=True)
    column_mapping = Column(JSON, nullable=False, default=dict)

    # Value written into the request_status column of each outbound row.
    request_status_value = Column(String(50), nullable=False, default="NEW")
    # Value written into the request_type column of each outbound row.
    request_type_value = Column(String(50), nullable=False, default="StockIndent", server_default="StockIndent")

    # Network-wide dispatch schedule (5-field cron, local timezone).
    schedule_cron = Column(String(100), nullable=True)

    # Kafka — brokers default from env KAFKA_BROKERS when blank; topic is global.
    kafka_brokers = Column(String(500), nullable=True)
    kafka_topic = Column(String(255), nullable=True)

    # Last-run summary (like DataMiningConfig)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String(30), nullable=True)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class StoreRequestSequence(Base):
    """Per-(store, day) counter backing the `{seq}` in a request number.

    Incremented under a row lock so concurrent runs never reuse a number.
    A new day naturally starts a fresh row at seq 1.
    """
    __tablename__ = "store_request_sequences"

    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True)
    seq_date = Column(Date, primary_key=True)
    last_seq = Column(Integer, nullable=False, default=0)


class OutboundDispatch(Base):
    """One dispatch of a store's indent for a period. Idempotent on (store, period)."""
    __tablename__ = "outbound_dispatches"
    __table_args__ = (
        UniqueConstraint("store_id", "period_start", name="uq_dispatch_store_period"),
        Index("ix_dispatch_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=True)
    request_number = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(Enum(DispatchStatus), nullable=False, default=DispatchStatus.pending)
    rows_written = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)


class OutboxEvent(Base):
    """Durable queue of Kafka messages (transactional outbox).

    Written in the same app-DB transaction that marks a dispatch `inserted`,
    then published by a separate poller → at-least-once delivery that survives
    Kafka downtime without dual-write inconsistency.
    """
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_status_created", "status", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    request_number = Column(String(64), nullable=False, index=True)
    topic = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=False)          # {"requestNumber": "..."}
    status = Column(Enum(OutboxStatus), nullable=False, default=OutboxStatus.unpublished)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
