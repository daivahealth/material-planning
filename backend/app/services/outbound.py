"""
Outbound dispatch service.

Flow (network-wide scheduled job → run_outbound_dispatch):
  1. Load the singleton OutboundSetting (must be enabled).
  2. For each store whose request_type == 'stock_indent':
       - generate the store's indents for the current period
       - allocate a per-(store, day) request number  (SI-{CODE}-{YYYYMMDD}-{seq})
       - write the indent lines to the external target table (idempotent replace)
       - mark the dispatch 'inserted' and enqueue a Kafka outbox event
  3. A separate poller (publish_outbox) publishes {"requestNumber": ...} to Kafka.

Consistency: the external-DB write and the app-DB state are a saga. The dispatch
row (with its reserved request number) is committed first, the external write is
idempotent on the request number, and the outbox event is written in the same
app-DB transaction that marks the dispatch 'inserted' — giving at-least-once
Kafka delivery without dual-write inconsistency.
"""
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

import pytz
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.models.indent import IndentReport, TriggerType
from app.models.item import Item
from app.models.settings import StoreSettings
from app.models.store import Store
from app.models.outbound import (
    OutboundSetting, StoreRequestSequence, OutboundDispatch, OutboxEvent,
    DispatchStatus, OutboxStatus,
)
from app.services.data_mining import get_source_engine
from app.services.indent import ItemLevelCache, generate_batch

log = logging.getLogger("outbound")

DEFAULT_TOPIC = "material_planning_event"
DEFAULT_REQUEST_TYPE = "StockIndent"
PURCHASE_REQUEST_TYPE = "PurchaseRequest"
_OUTBOUND_FIELDS = [
    "item_code", "store_code", "qty", "request_number",
    "request_type", "inserted_date", "request_status",
]
MAX_PUBLISH_ATTEMPTS = 10
# Unquoted SQL identifier: letter/underscore start, then word chars or $.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,62}$")


def _local_tz():
    return pytz.timezone(app_settings.timezone)


def _today() -> date:
    return datetime.now(_local_tz()).date()


def get_active_setting(db: Session) -> Optional[OutboundSetting]:
    """Return the singleton outbound setting (lowest id), or None."""
    return db.query(OutboundSetting).order_by(OutboundSetting.id.asc()).first()


def _resolve_brokers(setting: OutboundSetting) -> str:
    return (setting.kafka_brokers or app_settings.kafka_brokers or "").strip()


def _resolve_topic(setting: OutboundSetting) -> str:
    return (setting.kafka_topic or DEFAULT_TOPIC).strip()


def _mapped_col(setting: OutboundSetting, field: str) -> str:
    """Target column name for an internal field (identity mapping by default).
    A missing or blank mapping value falls back to the field name itself."""
    return (setting.column_mapping or {}).get(field) or field


# ─────────────────────────────────────────────
# Request-number sequencer  (per store, per day)
# ─────────────────────────────────────────────
def next_request_number(db: Session, store: Store, on_date: date, prefix: str = "SI") -> str:
    """Allocate the next request number for a store on a given day.

    ``prefix`` distinguishes document types (``SI`` stock indent, ``PR``
    purchase request). Concurrency-safe: the per-(store, day) counter row is
    locked FOR UPDATE; a first-time insert race is absorbed via a savepoint.
    """
    row = (
        db.query(StoreRequestSequence)
        .filter_by(store_id=store.id, seq_date=on_date)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        try:
            with db.begin_nested():
                row = StoreRequestSequence(store_id=store.id, seq_date=on_date, last_seq=0)
                db.add(row)
                db.flush()
        except IntegrityError:
            row = (
                db.query(StoreRequestSequence)
                .filter_by(store_id=store.id, seq_date=on_date)
                .with_for_update()
                .one()
            )
    row.last_seq += 1
    seq = row.last_seq
    code = store.code or str(store.id)
    return f"{prefix}-{code}-{on_date.strftime('%Y%m%d')}-{seq:04d}"


# ─────────────────────────────────────────────
# Per-store dispatch
# ─────────────────────────────────────────────
def _safe_identifier(name: str, kind: str) -> str:
    """Validate a SQL identifier that must be interpolated (table/column names
    cannot be bound parameters).

    The target table and column mapping are admin-supplied config, so without
    this they are a stored-injection vector into the external database. Accepts
    an optional schema qualifier: [schema.]name, each an unquoted identifier.
    """
    raw = (name or "").strip()
    if not raw:
        raise ValueError(f"Outbound {kind} is not configured")
    parts = raw.split(".")
    if len(parts) > 2:
        raise ValueError(f"Invalid outbound {kind} {name!r}")
    for p in parts:
        if not _IDENTIFIER_RE.match(p):
            raise ValueError(
                f"Invalid outbound {kind} {name!r}: identifiers must match "
                "[A-Za-z_][A-Za-z0-9_$]* (max 63 chars)"
            )
    return ".".join(parts)


def _write_to_target(engine, setting: OutboundSetting, request_number: str, rows: list) -> None:
    """Idempotent write: delete any existing rows for this request number, then
    insert the current lines. Runs in a single external-DB transaction."""
    table = _safe_identifier(setting.target_table, "target table")
    rn_col = _safe_identifier(_mapped_col(setting, "request_number"), "column mapping")
    cols = [_safe_identifier(_mapped_col(setting, f), "column mapping") for f in _OUTBOUND_FIELDS]
    placeholders = [f":{f}" for f in _OUTBOUND_FIELDS]
    insert_sql = text(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
    )
    delete_sql = text(f"DELETE FROM {table} WHERE {rn_col} = :rn")
    with engine.begin() as conn:
        conn.execute(delete_sql, {"rn": request_number})
        if rows:
            conn.execute(insert_sql, rows)


def dispatch_store(
    db: Session,
    setting: OutboundSetting,
    engine,
    store: Store,
    lines: list,
    period_start: date,
    period_end: Optional[date],
    on_date: date,
) -> dict:
    """Dispatch one store's indent lines. Idempotent on (store, period_start)."""
    disp = (
        db.query(OutboundDispatch)
        .filter_by(store_id=store.id, period_start=period_start)
        .with_for_update()
        .one_or_none()
    )
    if disp and disp.status in (DispatchStatus.inserted, DispatchStatus.published):
        return {"store_id": store.id, "request_number": disp.request_number,
                "rows": disp.rows_written, "status": "already_dispatched"}

    if disp is None:
        request_number = next_request_number(db, store, on_date)
        disp = OutboundDispatch(
            store_id=store.id, period_start=period_start, period_end=period_end,
            request_number=request_number, status=DispatchStatus.pending,
        )
        db.add(disp)
        db.flush()
    request_number = disp.request_number
    # Reserve the request number + dispatch row before touching the external DB.
    db.commit()

    inserted_at = datetime.now(_local_tz()).replace(tzinfo=None)  # local date + time
    request_type_value = getattr(setting, "request_type_value", None) or DEFAULT_REQUEST_TYPE
    # Only positive quantities are ever sent outbound. Callers already filter,
    # but this is the single choke point where rows are built — enforce here so
    # no zero/negative line can reach the target table by any path.
    rows = [{
        "item_code": item_code,
        "store_code": store.code,
        "qty": float(qty),
        "request_number": request_number,
        "request_type": request_type_value,
        "inserted_date": inserted_at,
        "request_status": setting.request_status_value,
    } for (item_code, qty) in lines if float(qty or 0) > 0]
    skipped_non_positive = len(lines) - len(rows)
    if skipped_non_positive:
        log.info("[store=%d] %s: skipped %d non-positive line(s)",
                 store.id, request_number, skipped_non_positive)

    try:
        _write_to_target(engine, setting, request_number, rows)
    except Exception as exc:
        disp.status = DispatchStatus.failed
        disp.error = str(exc)[:1000]
        db.commit()
        log.warning("[store=%d] outbound write failed for %s: %s", store.id, request_number, exc)
        return {"store_id": store.id, "request_number": request_number, "rows": 0, "status": "failed"}

    # Mark inserted and enqueue the Kafka event in the same app-DB transaction.
    disp.status = DispatchStatus.inserted
    disp.rows_written = len(rows)
    disp.error = None
    db.add(OutboxEvent(
        request_number=request_number,
        topic=_resolve_topic(setting),
        payload={"requestNumber": request_number},
        status=OutboxStatus.unpublished,
    ))
    db.commit()
    log.info("[store=%d] dispatched %s (%d rows)", store.id, request_number, len(rows))
    return {"store_id": store.id, "request_number": request_number, "rows": len(rows), "status": "dispatched"}


def _store_request_type(db: Session, store_id: int) -> str:
    ss = db.get(StoreSettings, store_id)
    return (ss.request_type if ss and ss.request_type else "stock_indent")


# ─────────────────────────────────────────────
# Network-wide dispatch job
# ─────────────────────────────────────────────
def run_outbound_dispatch(db: Session, as_of: Optional[date] = None) -> dict:
    """Generate + dispatch indents for all stock_indent stores. Idempotent."""
    setting = get_active_setting(db)
    if setting is None or not setting.enabled:
        log.info("outbound dispatch skipped: no enabled OutboundSetting")
        return {"skipped": True, "reason": "no_enabled_setting"}
    if not setting.target_table:
        return {"skipped": True, "reason": "no_target_table"}

    if as_of is None:
        as_of = _today()
    engine = get_source_engine(setting)

    stores = db.query(Store).all()
    # Item-scoped settings do not vary by store — load them once for the whole
    # run instead of once per store. Every store is then planned against the
    # same configuration snapshot.
    item_cache = ItemLevelCache(db)
    results = []
    dispatched = 0
    for store in stores:
        if _store_request_type(db, store.id) != "stock_indent":
            continue
        try:
            reports, _skipped = generate_batch(
                db, store.id, as_of, TriggerType.scheduler, item_cache=item_cache,
            )
        except Exception as exc:
            log.warning("[store=%d] generate_batch failed: %s", store.id, exc)
            continue
        positive = [r for r in reports if float(r.total_indent_qty or 0) > 0]
        if not positive:
            continue
        period_start = positive[0].period_start
        period_end = positive[0].period_end
        # Resolve item codes for the lines.
        item_ids = {r.item_id for r in positive}
        code_map = {
            i.id: i.code
            for i in db.query(Item.id, Item.code).filter(Item.id.in_(item_ids)).all()
        }
        lines = [(code_map.get(r.item_id, str(r.item_id)), r.total_indent_qty) for r in positive]
        res = dispatch_store(db, setting, engine, store, lines, period_start, period_end, as_of)
        results.append(res)
        if res["status"] == "dispatched":
            dispatched += 1

    setting.last_run_at = datetime.now(_local_tz())
    setting.last_run_status = "success"
    setting.last_error = None
    db.commit()

    # Best-effort immediate publish; the interval poller is the durable backstop.
    try:
        publish_outbox(db)
    except Exception as exc:
        log.info("post-dispatch publish attempt failed (will retry): %s", exc)

    return {"skipped": False, "stores_dispatched": dispatched, "results": results}


# ─────────────────────────────────────────────
# Kafka outbox publisher
# ─────────────────────────────────────────────
def publish_outbox(db: Session, limit: int = 500) -> dict:
    """Publish unpublished outbox events to Kafka; mark published. At-least-once."""
    setting = get_active_setting(db)
    brokers = _resolve_brokers(setting) if setting else app_settings.kafka_brokers.strip()
    if not brokers:
        return {"published": 0, "reason": "no_brokers"}

    events = (
        db.query(OutboxEvent)
        .filter(OutboxEvent.status == OutboxStatus.unpublished)
        .order_by(OutboxEvent.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    if not events:
        return {"published": 0}

    from kafka import KafkaProducer
    from kafka.errors import KafkaError

    try:
        producer = KafkaProducer(
            bootstrap_servers=[b.strip() for b in brokers.split(",") if b.strip()],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            retries=3,
            request_timeout_ms=10000,
        )
    except Exception as exc:
        # Broker unreachable: leave events queued for the next poll — no crash,
        # no per-event failure count (a down broker is not a bad message).
        db.rollback()
        log.warning("Kafka unavailable (%s) — %d event(s) remain queued", exc, len(events))
        return {"published": 0, "failed": 0, "reason": "broker_unavailable"}
    now = datetime.now(_local_tz())
    published = failed = 0
    try:
        for ev in events:
            try:
                md = producer.send(ev.topic, ev.payload).get(timeout=10)
                log.info(
                    "published %s -> %s[%s] @ offset %s",
                    ev.request_number, md.topic, md.partition, md.offset,
                )
                ev.status = OutboxStatus.published
                ev.published_at = now
                ev.last_error = None
                db.query(OutboundDispatch).filter(
                    OutboundDispatch.request_number == ev.request_number
                ).update({"status": DispatchStatus.published, "published_at": now})
                published += 1
            except KafkaError as exc:
                ev.attempts += 1
                ev.last_error = str(exc)[:1000]
                if ev.attempts >= MAX_PUBLISH_ATTEMPTS:
                    ev.status = OutboxStatus.failed
                failed += 1
                log.warning("outbox publish failed for %s: %s", ev.request_number, exc)
    finally:
        producer.flush()
        producer.close(timeout=5)
        db.commit()

    return {"published": published, "failed": failed}


# ─────────────────────────────────────────────
# Manual Purchase Request creation
# ─────────────────────────────────────────────
def create_purchase_request(db: Session, store_id: int, period_start, item_ids: list,
                            on_date: Optional[date] = None) -> dict:
    """Raise a Purchase Request for selected indent lines of a store+period.

    Writes the lines to the same outbound table with request_type=PurchaseRequest,
    marks each line pr_initiated=True (so it can't be PR'd again), and enqueues the
    request number for Kafka. Validates the store is configured for purchase_request.
    """
    setting = get_active_setting(db)
    if setting is None or not setting.target_table:
        raise ValueError("Outbound settings are not configured (target table missing).")
    store = db.get(Store, store_id)
    if store is None:
        raise ValueError("Store not found")
    if _store_request_type(db, store_id) != "purchase_request":
        raise ValueError(
            "Store is not configured for Purchase Request "
            "(set request_type = purchase_request in Store settings)."
        )
    if not item_ids:
        raise ValueError("No items selected")
    if on_date is None:
        on_date = _today()

    reports = (
        db.query(IndentReport)
        .filter(
            IndentReport.store_id == store_id,
            IndentReport.period_start == period_start,
            IndentReport.item_id.in_(item_ids),
            IndentReport.total_indent_qty > 0,
            IndentReport.pr_initiated.is_(False),
        )
        .with_for_update()
        .all()
    )
    if not reports:
        raise ValueError("No eligible indent lines for the selection (already PR-initiated or zero qty).")

    code_map = {
        i.id: i.code
        for i in db.query(Item.id, Item.code).filter(Item.id.in_([r.item_id for r in reports])).all()
    }
    request_number = next_request_number(db, store, on_date, prefix="PR")

    engine = get_source_engine(setting)
    inserted_at = datetime.now(_local_tz()).replace(tzinfo=None)
    # Only positive quantities go outbound (the query above already filters;
    # re-checked here so the rule holds wherever rows are built).
    rows = [{
        "item_code": code_map.get(r.item_id, str(r.item_id)),
        "store_code": store.code,
        "qty": float(r.total_indent_qty),
        "request_number": request_number,
        "request_type": PURCHASE_REQUEST_TYPE,
        "inserted_date": inserted_at,
        "request_status": setting.request_status_value,
    } for r in reports if float(r.total_indent_qty or 0) > 0]
    if not rows:
        raise ValueError("No eligible indent lines for the selection (all quantities are zero).")

    try:
        _write_to_target(engine, setting, request_number, rows)
    except Exception as exc:
        db.rollback()
        # Log the driver detail (host names, connection strings, SQL) server-side
        # only — the caller gets an actionable message with no internals.
        log.exception("outbound write failed for %s", request_number)
        raise ValueError(
            "Could not write to the outbound table. Check the Outbound Settings "
            "connection and target table, then try again."
        ) from exc

    for r in reports:
        r.pr_initiated = True
    db.add(OutboxEvent(
        request_number=request_number,
        topic=_resolve_topic(setting),
        payload={"requestNumber": request_number},
        status=OutboxStatus.unpublished,
    ))
    db.commit()

    try:
        publish_outbox(db)
    except Exception as exc:
        log.info("PR %s created; publish deferred: %s", request_number, exc)

    return {"request_number": request_number, "rows": len(rows),
            "item_ids": [r.item_id for r in reports]}
