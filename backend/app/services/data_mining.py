"""
Data mining service.

Responsibilities
----------------
* Encrypt / decrypt external-DB passwords with Fernet (MINING_SECRET_KEY).
* Build a SQLAlchemy engine for each external DB type (PostgreSQL, MySQL, Oracle).
* Test connections.
* Fetch rows from an external query with optional LIMIT/OFFSET pagination.
* Resolve item/store codes to internal IDs in bulk.
* Detect and skip duplicate rows using composite-key set-difference (per page).
* Bulk-insert new rows into the correct target model.
* Record a DataMiningRun log and update the config's last_run_* summary.
"""

from __future__ import annotations

import logging
import traceback
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from dateutil import parser as dateutil_parser

log = logging.getLogger("data_mining")

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import settings
from app.models.consumption import ClosingStock, ConsumptionRecord, OpenIndent
from app.models.data_mining import (
    DataMiningConfig,
    DataMiningRun,
    DataType,
    RunStatus,
)
from app.models.item import Item, ItemCategory, ItemGroup, Supplier


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    key = settings.mining_secret_key.encode()
    return Fernet(key)


def encrypt_password(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


# ---------------------------------------------------------------------------
# Value normalisation helpers
# ---------------------------------------------------------------------------

def _to_date(val: Any) -> Optional[date]:
    """Coerce a source value (date, datetime, str) to datetime.date, or None."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return dateutil_parser.parse(val.strip()).date()
        except (ValueError, OverflowError):
            return None
    return None


def _to_decimal(val: Any) -> Optional[Decimal]:
    """Coerce a source value to Decimal, or None on failure."""
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _code(val: Any) -> str:
    """Normalise a source code value: stringify and strip whitespace."""
    return str(val).strip() if val is not None else ""


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------

# Fail fast when a source DB is unreachable, instead of hanging on the OS
# default TCP timeout (which can leave a run stuck in `running` for minutes).
SOURCE_CONNECT_TIMEOUT_S = 15


def get_source_engine(config: DataMiningConfig) -> Engine:
    plain_pw = decrypt_password(config.encrypted_password)
    connect_args: Dict[str, Any] = {}

    if config.db_type.value == "postgresql":
        url = (
            f"postgresql+psycopg2://{config.username}:{plain_pw}"
            f"@{config.host}:{config.port}/{config.database_name}"
        )
        connect_args["connect_timeout"] = SOURCE_CONNECT_TIMEOUT_S
    elif config.db_type.value == "mysql":
        url = (
            f"mysql+pymysql://{config.username}:{plain_pw}"
            f"@{config.host}:{config.port}/{config.database_name}"
        )
        connect_args["connect_timeout"] = SOURCE_CONNECT_TIMEOUT_S
    elif config.db_type.value == "oracle":
        url = (
            f"oracle+oracledb://{config.username}:{plain_pw}"
            f"@{config.host}:{config.port}/?service_name={config.database_name}"
        )
        connect_args["tcp_connect_timeout"] = SOURCE_CONNECT_TIMEOUT_S
    else:
        raise ValueError(f"Unsupported db_type: {config.db_type}")

    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection(config: DataMiningConfig) -> Dict[str, Any]:
    log.info(
        "[config=%d name=%r] Testing connection to %s %s@%s:%s/%s",
        config.id, config.name, config.db_type.value,
        config.username, config.host, config.port, config.database_name,
    )
    try:
        engine = get_source_engine(config)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        log.info("[config=%d] Connection test PASSED", config.id)
        return {"success": True, "message": "Connection successful."}
    except Exception as exc:
        log.warning("[config=%d] Connection test FAILED: %s", config.id, exc)
        return {"success": False, "message": str(exc)}


# ---------------------------------------------------------------------------
# Paginated query execution
# ---------------------------------------------------------------------------

def _build_paged_query(db_type: str, base_query: str, page_size: int, offset: int) -> str:
    """Wrap a user query in a pagination envelope suited to the target dialect."""
    if db_type == "oracle":
        # Oracle doesn't support LIMIT/OFFSET directly in older versions
        start = offset
        end = offset + page_size
        return (
            f"SELECT * FROM ("
            f"SELECT _q.*, ROWNUM AS _rnum FROM ({base_query}) _q "
            f"WHERE ROWNUM <= {end}"
            f") WHERE _rnum > {start}"
        )
    # PostgreSQL and MySQL both support standard LIMIT / OFFSET
    return f"SELECT * FROM ({base_query}) AS _dm_q LIMIT {page_size} OFFSET {offset}"


def _fetch_paginated(
    engine: Engine,
    db_type: str,
    query: str,
    page_size: int,
) -> Iterator[List[Dict[str, Any]]]:
    """
    Yield lists of row-dicts, one list per page.
    If page_size == 0 the entire result is returned in a single yield.
    """
    with engine.connect() as conn:
        if page_size == 0:
            log.debug("[fetch] page_size=0 — fetching all rows in one request")
            result = conn.execute(text(query))
            keys = list(result.keys())
            rows = [dict(zip(keys, row)) for row in result.fetchall()]
            log.info("[fetch] no-pagination fetch returned %d rows (columns: %s)", len(rows), keys)
            if rows:
                yield rows
            return

        offset = 0
        page_num = 0
        while True:
            paged_sql = _build_paged_query(db_type, query, page_size, offset)
            log.debug("[fetch] page=%d offset=%d page_size=%d", page_num, offset, page_size)
            result = conn.execute(text(paged_sql))
            keys = list(result.keys())
            rows = [dict(zip(keys, row)) for row in result.fetchall()]
            log.info(
                "[fetch] page=%d offset=%d → %d rows (columns: %s)",
                page_num, offset, len(rows), keys,
            )
            if not rows:
                log.debug("[fetch] empty page — stopping pagination")
                break
            yield rows
            if len(rows) < page_size:
                log.debug("[fetch] partial page (%d < %d) — last page", len(rows), page_size)
                break
            offset += page_size
            page_num += 1


# ---------------------------------------------------------------------------
# Lookup dicts (pre-loaded once per run for performance)
# ---------------------------------------------------------------------------

def _get_lookup_dicts(db: Session) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Return {item_code: item_id} and {store_code: store_id} for the whole table."""
    item_by_code: Dict[str, int] = {
        row.code: row.id for row in db.query(Item.code, Item.id).all()
    }
    from app.models.store import Store

    store_by_code: Dict[str, int] = {
        row.code: row.id for row in db.query(Store.code, Store.id).all()
    }
    log.info(
        "[lookup] loaded %d item codes and %d store codes from app DB",
        len(item_by_code), len(store_by_code),
    )
    return item_by_code, store_by_code


# ---------------------------------------------------------------------------
# Existing-key bulk lookup (dedup)
# ---------------------------------------------------------------------------

def _existing_consumption_keys(
    db: Session,
    tuples: List[Tuple[int, int, Any]],
) -> Set[Tuple[int, int, Any]]:
    if not tuples:
        return set()
    rows = (
        db.query(
            ConsumptionRecord.item_id,
            ConsumptionRecord.store_id,
            ConsumptionRecord.date,
        )
        .filter(
            ConsumptionRecord.item_id.in_({t[0] for t in tuples}),
            ConsumptionRecord.store_id.in_({t[1] for t in tuples}),
        )
        .all()
    )
    return {(r.item_id, r.store_id, r.date) for r in rows}


def _existing_closing_stock_keys(
    db: Session,
    tuples: List[Tuple[int, int, Any]],
) -> Set[Tuple[int, int, Any]]:
    if not tuples:
        return set()
    rows = (
        db.query(
            ClosingStock.item_id,
            ClosingStock.store_id,
            ClosingStock.date,
        )
        .filter(
            ClosingStock.item_id.in_({t[0] for t in tuples}),
            ClosingStock.store_id.in_({t[1] for t in tuples}),
        )
        .all()
    )
    return {(r.item_id, r.store_id, r.date) for r in rows}


def _existing_open_indent_keys(
    db: Session,
    tuples: List[Tuple[int, int, Any]],
) -> Set[Tuple[int, int, Any]]:
    if not tuples:
        return set()
    rows = (
        db.query(
            OpenIndent.item_id,
            OpenIndent.store_id,
            OpenIndent.as_of_date,
        )
        .filter(
            OpenIndent.item_id.in_({t[0] for t in tuples}),
            OpenIndent.store_id.in_({t[1] for t in tuples}),
        )
        .all()
    )
    return {(r.item_id, r.store_id, r.as_of_date) for r in rows}


def _write_timeseries_page(
    db: Session,
    model,
    key_columns: tuple,
    candidate_tuples: List[Tuple[int, int, Any]],
    mapped: List[Dict[str, Any]],
    existing: Set[Tuple[int, int, Any]],
    write_mode: str,
    run: DataMiningRun,
    purged_dates: Optional[Set[Any]] = None,
    page_num: int = 0,
) -> Tuple[int, int]:
    """Persist one page of time-series rows per the config's write mode.

    skip (default): insert only keys not already present; count the rest skipped.
    overwrite:      last-value-wins per key — delete any existing rows for the
                    page's keys, then insert the deduplicated mapped rows.
    replace_date:   snapshot semantics — delete the WHOLE day's data (every
                    store, every item) for each date the feed carries, then
                    insert what the source supplied.

    Why replace_date exists: `overwrite` only touches keys present in the feed,
    so an item the source has stopped reporting keeps its old row forever — the
    planner then reads a stale closing stock / open indent. Wiping the day first
    guarantees the stored day matches the feed exactly.

    The DELETE fires **once per run**, on the first page (`page_num == 0`), and
    `purged_dates` records what has already been cleared. Both guards matter:
    without them a later page would delete the rows earlier pages of the same
    run had just inserted.

    Returns (written, skipped).
    """
    from sqlalchemy import tuple_

    if (write_mode or "skip") == "replace_date":
        # Collapse within-page duplicate keys, keeping the last occurrence.
        by_key: Dict[Tuple[int, int, Any], Dict[str, Any]] = {}
        for k, r in zip(candidate_tuples, mapped):
            by_key[k] = r
        if purged_dates is None:
            purged_dates = set()
        date_col = key_columns[2]
        # Fire the wipe only on the first page of the run; later pages just
        # insert into the day this already cleared.
        if page_num == 0:
            to_purge = {k[2] for k in by_key} - purged_dates
            for on_date in to_purge:
                deleted = db.query(model).filter(date_col == on_date).delete(
                    synchronize_session=False
                )
                purged_dates.add(on_date)
                log.info(
                    "[run=%s] replace_date: cleared %d existing %s row(s) for %s",
                    getattr(run, "id", "?"), deleted, model.__tablename__, on_date,
                )
            if to_purge:
                db.flush()
        rows = list(by_key.values())
        if rows:
            db.bulk_insert_mappings(model, rows)
            db.flush()
        run.rows_inserted += len(rows)
        return len(rows), 0

    if (write_mode or "skip") == "overwrite":
        # Collapse within-page duplicate keys, keeping the last occurrence.
        by_key: Dict[Tuple[int, int, Any], Dict[str, Any]] = {}
        for k, r in zip(candidate_tuples, mapped):
            by_key[k] = r
        dup_keys = [k for k in by_key if k in existing]
        if dup_keys:
            db.query(model).filter(tuple_(*key_columns).in_(dup_keys)).delete(
                synchronize_session=False
            )
            db.flush()
        rows = list(by_key.values())
        if rows:
            db.bulk_insert_mappings(model, rows)
            db.flush()
        run.rows_inserted += len(rows)
        return len(rows), 0

    new_rows = [r for r, k in zip(mapped, candidate_tuples) if k not in existing]
    skipped = len(mapped) - len(new_rows)
    run.rows_skipped += skipped
    if new_rows:
        db.bulk_insert_mappings(model, new_rows)
        db.flush()
    run.rows_inserted += len(new_rows)
    return len(new_rows), skipped


# ---------------------------------------------------------------------------
# Per-type miners
# ---------------------------------------------------------------------------

def _mine_consumption(
    source_engine: Engine,
    config: DataMiningConfig,
    db: Session,
    run: DataMiningRun,
    item_by_code: Dict[str, int],
    store_by_code: Dict[str, int],
) -> None:
    m = config.column_mapping
    log.info("[config=%d run=%d] Starting consumption mining. mapping=%s", config.id, run.id, m)
    page_num = 0
    # replace_date state for THIS run: dates already wiped. The delete fires on
    # the first page only, so later pages cannot remove rows this run inserted.
    purged_dates: Set[Any] = set()

    for page in _fetch_paginated(
        source_engine, config.db_type.value, config.query, config.page_size
    ):
        run.rows_fetched += len(page)
        candidate_tuples: List[Tuple[int, int, Any]] = []
        mapped: List[Dict[str, Any]] = []
        skip_no_item = skip_no_store = skip_bad_date = skip_bad_qty = 0

        for row in page:
            raw_item = row.get(m["item_code"])
            raw_store = row.get(m["store_code"])
            item_id = item_by_code.get(_code(raw_item))
            store_id = store_by_code.get(_code(raw_store))
            if item_id is None:
                skip_no_item += 1
                log.debug(
                    "[config=%d run=%d] SKIP item not found: raw_item=%r (mapped from column %r)",
                    config.id, run.id, raw_item, m["item_code"],
                )
                run.rows_skipped += 1
                continue
            if store_id is None:
                skip_no_store += 1
                log.debug(
                    "[config=%d run=%d] SKIP store not found: raw_store=%r (mapped from column %r)",
                    config.id, run.id, raw_store, m["store_code"],
                )
                run.rows_skipped += 1
                continue
            date_val = _to_date(row.get(m["date"]))
            if date_val is None:
                skip_bad_date += 1
                log.debug(
                    "[config=%d run=%d] SKIP bad/null date: raw=%r (column %r)",
                    config.id, run.id, row.get(m["date"]), m["date"],
                )
                run.rows_skipped += 1
                continue
            qty = _to_decimal(row.get(m["quantity"]))
            if qty is None:
                skip_bad_qty += 1
                log.debug(
                    "[config=%d run=%d] SKIP bad/null quantity: raw=%r (column %r)",
                    config.id, run.id, row.get(m["quantity"]), m["quantity"],
                )
                run.rows_skipped += 1
                continue
            candidate_tuples.append((item_id, store_id, date_val))
            mapped.append({"item_id": item_id, "store_id": store_id, "date": date_val, "quantity": qty})

        if skip_no_item or skip_no_store or skip_bad_date or skip_bad_qty:
            log.warning(
                "[config=%d run=%d] page=%d skip summary — no_item=%d no_store=%d bad_date=%d bad_qty=%d",
                config.id, run.id, page_num,
                skip_no_item, skip_no_store, skip_bad_date, skip_bad_qty,
            )

        existing = _existing_consumption_keys(db, candidate_tuples)
        log.debug(
            "[config=%d run=%d] page=%d dedup: %d candidates, %d already exist",
            config.id, run.id, page_num, len(candidate_tuples), len(existing),
        )
        written, skipped_dedup = _write_timeseries_page(
            db, ConsumptionRecord,
            (ConsumptionRecord.item_id, ConsumptionRecord.store_id, ConsumptionRecord.date),
            candidate_tuples, mapped, existing, config.write_mode, run,
            purged_dates, page_num,
        )
        log.info(
            "[config=%d run=%d] page=%d mode=%s → written=%d skipped_dedup=%d",
            config.id, run.id, page_num, config.write_mode, written, skipped_dedup,
        )
        page_num += 1


def _mine_closing_stock(
    source_engine: Engine,
    config: DataMiningConfig,
    db: Session,
    run: DataMiningRun,
    item_by_code: Dict[str, int],
    store_by_code: Dict[str, int],
) -> None:
    m = config.column_mapping
    log.info("[config=%d run=%d] Starting closing_stock mining. mapping=%s", config.id, run.id, m)
    page_num = 0
    # replace_date state for THIS run: dates already wiped. The delete fires on
    # the first page only, so later pages cannot remove rows this run inserted.
    purged_dates: Set[Any] = set()

    for page in _fetch_paginated(
        source_engine, config.db_type.value, config.query, config.page_size
    ):
        run.rows_fetched += len(page)
        candidate_tuples: List[Tuple[int, int, Any]] = []
        mapped: List[Dict[str, Any]] = []
        skip_no_item = skip_no_store = skip_bad_date = skip_bad_qty = 0

        for row in page:
            raw_item = row.get(m["item_code"])
            raw_store = row.get(m["store_code"])
            item_id = item_by_code.get(_code(raw_item))
            store_id = store_by_code.get(_code(raw_store))
            if item_id is None:
                skip_no_item += 1
                log.debug(
                    "[config=%d run=%d] SKIP item not found: raw_item=%r (column %r)",
                    config.id, run.id, raw_item, m["item_code"],
                )
                run.rows_skipped += 1
                continue
            if store_id is None:
                skip_no_store += 1
                log.debug(
                    "[config=%d run=%d] SKIP store not found: raw_store=%r (column %r)",
                    config.id, run.id, raw_store, m["store_code"],
                )
                run.rows_skipped += 1
                continue
            date_val = _to_date(row.get(m["date"]))
            if date_val is None:
                skip_bad_date += 1
                log.debug(
                    "[config=%d run=%d] SKIP bad/null date: raw=%r (column %r)",
                    config.id, run.id, row.get(m["date"]), m["date"],
                )
                run.rows_skipped += 1
                continue
            qty = _to_decimal(row.get(m["quantity"]))
            if qty is None:
                skip_bad_qty += 1
                log.debug(
                    "[config=%d run=%d] SKIP bad/null quantity: raw=%r (column %r)",
                    config.id, run.id, row.get(m["quantity"]), m["quantity"],
                )
                run.rows_skipped += 1
                continue
            candidate_tuples.append((item_id, store_id, date_val))
            mapped.append({"item_id": item_id, "store_id": store_id, "date": date_val, "quantity": qty})

        if skip_no_item or skip_no_store or skip_bad_date or skip_bad_qty:
            log.warning(
                "[config=%d run=%d] page=%d skip summary — no_item=%d no_store=%d bad_date=%d bad_qty=%d",
                config.id, run.id, page_num,
                skip_no_item, skip_no_store, skip_bad_date, skip_bad_qty,
            )

        existing = _existing_closing_stock_keys(db, candidate_tuples)
        log.debug(
            "[config=%d run=%d] page=%d dedup: %d candidates, %d already exist",
            config.id, run.id, page_num, len(candidate_tuples), len(existing),
        )
        written, skipped_dedup = _write_timeseries_page(
            db, ClosingStock,
            (ClosingStock.item_id, ClosingStock.store_id, ClosingStock.date),
            candidate_tuples, mapped, existing, config.write_mode, run,
            purged_dates, page_num,
        )
        log.info(
            "[config=%d run=%d] page=%d mode=%s → written=%d skipped_dedup=%d",
            config.id, run.id, page_num, config.write_mode, written, skipped_dedup,
        )
        page_num += 1


def _mine_open_indent(
    source_engine: Engine,
    config: DataMiningConfig,
    db: Session,
    run: DataMiningRun,
    item_by_code: Dict[str, int],
    store_by_code: Dict[str, int],
) -> None:
    m = config.column_mapping
    log.info("[config=%d run=%d] Starting open_indent mining. mapping=%s", config.id, run.id, m)
    page_num = 0
    # replace_date state for THIS run: dates already wiped. The delete fires on
    # the first page only, so later pages cannot remove rows this run inserted.
    purged_dates: Set[Any] = set()

    for page in _fetch_paginated(
        source_engine, config.db_type.value, config.query, config.page_size
    ):
        run.rows_fetched += len(page)
        candidate_tuples: List[Tuple[int, int, Any]] = []
        mapped: List[Dict[str, Any]] = []
        skip_no_item = skip_no_store = skip_bad_date = skip_bad_qty = 0

        for row in page:
            raw_item = row.get(m["item_code"])
            raw_store = row.get(m["store_code"])
            item_id = item_by_code.get(_code(raw_item))
            store_id = store_by_code.get(_code(raw_store))
            if item_id is None:
                skip_no_item += 1
                log.debug(
                    "[config=%d run=%d] SKIP item not found: raw_item=%r (column %r)",
                    config.id, run.id, raw_item, m["item_code"],
                )
                run.rows_skipped += 1
                continue
            if store_id is None:
                skip_no_store += 1
                log.debug(
                    "[config=%d run=%d] SKIP store not found: raw_store=%r (column %r)",
                    config.id, run.id, raw_store, m["store_code"],
                )
                run.rows_skipped += 1
                continue
            date_val = _to_date(row.get(m["as_of_date"]))
            if date_val is None:
                skip_bad_date += 1
                log.debug(
                    "[config=%d run=%d] SKIP bad/null date: raw=%r (column %r)",
                    config.id, run.id, row.get(m["as_of_date"]), m["as_of_date"],
                )
                run.rows_skipped += 1
                continue
            qty = _to_decimal(row.get(m["quantity"]))
            if qty is None:
                skip_bad_qty += 1
                log.debug(
                    "[config=%d run=%d] SKIP bad/null quantity: raw=%r (column %r)",
                    config.id, run.id, row.get(m["quantity"]), m["quantity"],
                )
                run.rows_skipped += 1
                continue
            candidate_tuples.append((item_id, store_id, date_val))
            mapped.append({"item_id": item_id, "store_id": store_id, "as_of_date": date_val, "quantity": qty})

        if skip_no_item or skip_no_store or skip_bad_date or skip_bad_qty:
            log.warning(
                "[config=%d run=%d] page=%d skip summary — no_item=%d no_store=%d bad_date=%d bad_qty=%d",
                config.id, run.id, page_num,
                skip_no_item, skip_no_store, skip_bad_date, skip_bad_qty,
            )

        existing = _existing_open_indent_keys(db, candidate_tuples)
        log.debug(
            "[config=%d run=%d] page=%d dedup: %d candidates, %d already exist",
            config.id, run.id, page_num, len(candidate_tuples), len(existing),
        )
        written, skipped_dedup = _write_timeseries_page(
            db, OpenIndent,
            (OpenIndent.item_id, OpenIndent.store_id, OpenIndent.as_of_date),
            candidate_tuples, mapped, existing, config.write_mode, run,
            purged_dates, page_num,
        )
        log.info(
            "[config=%d run=%d] page=%d mode=%s → written=%d skipped_dedup=%d",
            config.id, run.id, page_num, config.write_mode, written, skipped_dedup,
        )
        page_num += 1


def _mine_item(
    source_engine: Engine,
    config: DataMiningConfig,
    db: Session,
    run: DataMiningRun,
) -> None:
    m = config.column_mapping
    log.info("[config=%d run=%d] Starting item mining. mapping=%s", config.id, run.id, m)
    existing_codes: Set[str] = {
        row.code for row in db.query(Item.code).all()
    }
    log.info("[config=%d run=%d] %d item codes already in app DB", config.id, run.id, len(existing_codes))
    page_num = 0
    for page in _fetch_paginated(
        source_engine, config.db_type.value, config.query, config.page_size
    ):
        run.rows_fetched += len(page)
        new_rows: List[Dict[str, Any]] = []
        overwrite = (config.write_mode or "skip") == "overwrite"

        existing_items: Dict[str, Item] = {}
        if overwrite:
            page_codes = {str(r.get(m["code"], "") or "").strip() for r in page}
            page_codes.discard("")
            if page_codes:
                existing_items = {
                    it.code: it for it in db.query(Item).filter(Item.code.in_(page_codes)).all()
                }

        inserted = updated = skipped = 0
        for row in page:
            code = str(row.get(m["code"], "") or "").strip()
            if not code:
                skipped += 1
                continue
            is_existing = code in existing_codes
            if is_existing and not overwrite:
                skipped += 1
                continue

            group_id: Optional[int] = None
            if "group_name" in m:
                gname = str(row.get(m["group_name"], "")).strip()
                if gname:
                    grp = db.query(ItemGroup).filter_by(name=gname).first()
                    if not grp:
                        grp = ItemGroup(name=gname)
                        db.add(grp)
                        db.flush()
                    group_id = grp.id

            category_id: Optional[int] = None
            if "category_name" in m:
                cname = str(row.get(m["category_name"], "")).strip()
                if cname:
                    cat = db.query(ItemCategory).filter_by(name=cname).first()
                    if not cat:
                        cat = ItemCategory(name=cname)
                        db.add(cat)
                        db.flush()
                    category_id = cat.id

            unit = "Nos"
            if "unit" in m:
                unit = str(row.get(m["unit"], "Nos")).strip() or "Nos"
            name = str(row.get(m["name"], code))

            if is_existing:  # overwrite: update the existing item in place
                it = existing_items.get(code)
                if it is not None:
                    it.name = name
                    it.unit = unit
                    if group_id is not None:
                        it.group_id = group_id
                    if category_id is not None:
                        it.category_id = category_id
                    updated += 1
                else:
                    skipped += 1
            else:
                new_rows.append({
                    "code": code, "name": name, "unit": unit,
                    "group_id": group_id, "category_id": category_id,
                })
                existing_codes.add(code)
                inserted += 1

        if new_rows:
            db.bulk_insert_mappings(Item, new_rows)
            db.flush()
        run.rows_inserted += inserted + updated
        run.rows_skipped += skipped
        log.info(
            "[config=%d run=%d] page=%d mode=%s → inserted=%d updated=%d skipped=%d",
            config.id, run.id, page_num, config.write_mode, inserted, updated, skipped,
        )
        page_num += 1


def _mine_supplier(
    source_engine: Engine,
    config: DataMiningConfig,
    db: Session,
    run: DataMiningRun,
) -> None:
    m = config.column_mapping
    log.info("[config=%d run=%d] Starting supplier mining. mapping=%s", config.id, run.id, m)
    existing_codes: Set[str] = {
        row.code for row in db.query(Supplier.code).all()
    }
    log.info("[config=%d run=%d] %d supplier codes already in app DB", config.id, run.id, len(existing_codes))
    page_num = 0
    for page in _fetch_paginated(
        source_engine, config.db_type.value, config.query, config.page_size
    ):
        run.rows_fetched += len(page)
        new_rows: List[Dict[str, Any]] = []
        overwrite = (config.write_mode or "skip") == "overwrite"

        existing_suppliers: Dict[str, Supplier] = {}
        if overwrite:
            page_codes = {str(r.get(m["code"], "") or "").strip() for r in page}
            page_codes.discard("")
            if page_codes:
                existing_suppliers = {
                    s.code: s for s in db.query(Supplier).filter(Supplier.code.in_(page_codes)).all()
                }

        inserted = updated = skipped = 0
        for row in page:
            code = str(row.get(m["code"], "") or "").strip()
            if not code:
                skipped += 1
                continue
            is_existing = code in existing_codes
            if is_existing and not overwrite:
                skipped += 1
                continue

            lead_time = 7
            if "lead_time_days" in m:
                try:
                    lead_time = int(row.get(m["lead_time_days"], 7))
                except (ValueError, TypeError):
                    lead_time = 7
            name = str(row.get(m["name"], code))

            if is_existing:  # overwrite: update the existing supplier in place
                s = existing_suppliers.get(code)
                if s is not None:
                    s.name = name
                    s.lead_time_days = lead_time
                    updated += 1
                else:
                    skipped += 1
            else:
                new_rows.append({"code": code, "name": name, "lead_time_days": lead_time})
                existing_codes.add(code)
                inserted += 1

        if new_rows:
            db.bulk_insert_mappings(Supplier, new_rows)
            db.flush()
        run.rows_inserted += inserted + updated
        run.rows_skipped += skipped
        log.info(
            "[config=%d run=%d] page=%d mode=%s → inserted=%d updated=%d skipped=%d",
            config.id, run.id, page_num, config.write_mode, inserted, updated, skipped,
        )
        page_num += 1


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

_MINERS = {
    DataType.consumption: _mine_consumption,
    DataType.closing_stock: _mine_closing_stock,
    DataType.open_indent: _mine_open_indent,
}
_CODE_FREE_MINERS = {
    DataType.item: _mine_item,
    DataType.supplier: _mine_supplier,
}


def reset_orphaned_runs(db: Session) -> int:
    """Mark runs/configs left in `running` (e.g. by a restart or crash) as
    errored, so the 'already running' guard can't block them forever.

    Returns the number of runs reset. Call once at startup.
    """
    stuck_runs = db.query(DataMiningRun).filter(DataMiningRun.status == RunStatus.running).all()
    for run in stuck_runs:
        run.status = RunStatus.error
        run.ended_at = datetime.now(timezone.utc)
        if not run.error_message:
            run.error_message = "Run interrupted (server restart or crash) — marked failed at startup."
    n_cfg = (
        db.query(DataMiningConfig)
        .filter(DataMiningConfig.last_run_status == RunStatus.running)
        .update({DataMiningConfig.last_run_status: RunStatus.error}, synchronize_session=False)
    )
    if stuck_runs or n_cfg:
        db.commit()
        log.warning("Reset %d orphaned run(s) and %d config(s) stuck in 'running'", len(stuck_runs), n_cfg)
    return len(stuck_runs)


def run_mining_config(config_id: int, db: Session) -> DataMiningRun:
    """
    Execute a single DataMiningConfig.  Creates a DataMiningRun record,
    runs the appropriate type-specific miner, and updates the config's
    last_run_* summary columns.  Safe to call from a background thread.
    """
    config: Optional[DataMiningConfig] = db.get(DataMiningConfig, config_id)
    if config is None:
        log.error("[config=%d] Config not found — aborting run", config_id)
        raise ValueError(f"DataMiningConfig {config_id} not found")

    # Guard: skip if already running
    if config.last_run_status == RunStatus.running:
        log.warning("[config=%d name=%r] Already running — skipping duplicate trigger", config_id, config.name)
        raise RuntimeError(f"Config {config_id} is already running")

    log.info(
        "[config=%d name=%r] Run starting. data_type=%s db=%s %s@%s:%s/%s page_size=%d",
        config.id, config.name, config.data_type.value, config.db_type.value,
        config.username, config.host, config.port, config.database_name, config.page_size,
    )

    run = DataMiningRun(
        config_id=config_id,
        status=RunStatus.running,
        rows_fetched=0,
        rows_inserted=0,
        rows_skipped=0,
    )
    db.add(run)
    config.last_run_status = RunStatus.running
    config.last_run_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)

    source_engine: Optional[Engine] = None
    try:
        log.debug("[config=%d run=%d] Building source engine", config.id, run.id)
        source_engine = get_source_engine(config)

        if config.data_type in _MINERS:
            item_by_code, store_by_code = _get_lookup_dicts(db)
            _MINERS[config.data_type](
                source_engine, config, db, run, item_by_code, store_by_code
            )
        elif config.data_type in _CODE_FREE_MINERS:
            _CODE_FREE_MINERS[config.data_type](source_engine, config, db, run)
        else:
            raise ValueError(f"No miner for data_type={config.data_type}")

        db.commit()
        run.status = RunStatus.success
        log.info(
            "[config=%d run=%d] Run SUCCESS — fetched=%d inserted=%d skipped=%d",
            config.id, run.id, run.rows_fetched, run.rows_inserted, run.rows_skipped,
        )

    except Exception:
        db.rollback()
        run.status = RunStatus.error
        run.error_message = traceback.format_exc()
        log.error(
            "[config=%d run=%d] Run FAILED:\n%s",
            config.id, run.id, run.error_message,
        )

    finally:
        if source_engine:
            source_engine.dispose()
        run.ended_at = datetime.now(timezone.utc)

        # Update config summary
        config.last_run_status = run.status
        config.last_run_at = run.ended_at
        config.last_rows_fetched = run.rows_fetched
        config.last_rows_inserted = run.rows_inserted
        config.last_rows_skipped = run.rows_skipped
        config.last_error = run.error_message
        db.add(run)
        db.add(config)
        db.commit()
        db.refresh(run)

    return run
