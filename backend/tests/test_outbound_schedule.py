"""
The outbound dispatch run honouring per-store indent schedules (issue #15).

These cover the loop itself rather than the schedule arithmetic (see
test_indent_schedule.py): which stores a run touches, what it does to a
purchase-request store, that one store's failure doesn't take the run with it,
and that an hourly job which finds nothing due stays cheap.

The external target DB and Kafka are stubbed — everything on the app side
(generation, request numbering, dispatch rows, the outbox event) runs for real.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import pytz

from app.models.consumption import ClosingStock, ConsumptionRecord
from app.models.hospital import Hospital
from app.models.item import Item
from app.models.indent import IndentReport
from app.models.outbound import OutboundDispatch, OutboundSetting, DbType
from app.models.settings import HospitalSettings, StoreSettings
from app.models.store import Store
from app.services import indent_schedule as sched
from app.services import outbound as outbound_svc

TZ = pytz.timezone("Asia/Kolkata")
TODAY = date(2026, 11, 24)


def _cron_for_this_hour(offset_hours: int = 0) -> str:
    """A daily cron whose fire lands in (or outside) the current window.

    The run reads the real clock, so the schedules are written relative to it
    instead of freezing time: offset 0 is due on this tick, -2 fired two hours
    ago and is past the one-hour window.
    """
    hour = (datetime.now(TZ).hour + offset_hours) % 24
    return f"0 {hour} * * *"


@pytest.fixture
def network(db):
    """Two stock-indent stores and one purchase-request store, each with 30
    days of consumption so generation produces a positive quantity."""
    h = Hospital(code="H1", name="H")
    db.add(h)
    db.flush()
    db.add(HospitalSettings(
        hospital_id=h.id, lookback_days=30, indent_duration_days=30,
        safety_stock_days=3.0, fsn_period_days=365, fsn_schedule_days=30,
        projection_formula="standard", indent_schedule_cron="0 6 * * *",
    ))
    stores = {}
    for code, request_type in (("SI1", "stock_indent"), ("SI2", "stock_indent"),
                               ("PR1", "purchase_request")):
        store = Store(hospital_id=h.id, code=code, name=code)
        db.add(store)
        db.flush()
        db.add(StoreSettings(store_id=store.id, request_type=request_type))
        stores[code] = store

    item = Item(code="DRG", name="Drug", unit="Tabs")
    db.add(item)
    db.flush()
    for store in stores.values():
        for d in range(30):
            db.add(ConsumptionRecord(
                item_id=item.id, store_id=store.id,
                date=TODAY - timedelta(days=30 - d), quantity=Decimal("10"),
            ))
        db.add(ClosingStock(item_id=item.id, store_id=store.id,
                            date=TODAY, quantity=Decimal("50")))

    db.add(OutboundSetting(
        enabled=True, db_type=DbType.postgresql, host="h", port=5432,
        database_name="d", username="u", encrypted_password="x",
        target_table="outbound_rows", column_mapping={},
        request_status_value="NEW", schedule_cron="0 * * * *",
    ))
    db.flush()
    db.commit()
    return {"hospital": h, "stores": stores, "item": item}


@pytest.fixture
def stub_target(monkeypatch):
    """Stub the external DB write and the Kafka publish; record what was sent."""
    written = []

    def fake_write(engine, setting, request_number, rows):
        written.append({"request_number": request_number, "rows": list(rows)})

    monkeypatch.setattr(outbound_svc, "get_source_engine", lambda setting: object())
    monkeypatch.setattr(outbound_svc, "_write_to_target", fake_write)
    monkeypatch.setattr(outbound_svc, "publish_outbox", lambda db, **kw: {"published": 0})
    return written


def _set_cron(db, store, cron):
    ss = db.get(StoreSettings, store.id)
    ss.indent_schedule_cron = cron
    db.commit()


# ─────────────────────────────────────────────
# Which stores a scheduled run touches
# ─────────────────────────────────────────────
def test_only_due_stores_are_generated(db, network, stub_target):
    due, not_due = network["stores"]["SI1"], network["stores"]["SI2"]
    _set_cron(db, due, _cron_for_this_hour(0))
    _set_cron(db, not_due, _cron_for_this_hour(-2))
    _set_cron(db, network["stores"]["PR1"], _cron_for_this_hour(-2))

    result = outbound_svc.run_outbound_dispatch(db, TODAY)

    assert result["stores_due"] == 1
    assert result["stores_generated"] == 1
    assert result["stores_dispatched"] == 1
    assert result["skipped_not_due"] == 2
    assert {r["store_id"] for r in result["results"]} == {due.id}
    # ...and the store that wasn't due has no plan at all.
    assert db.query(IndentReport).filter_by(store_id=not_due.id).count() == 0


def test_second_run_in_the_same_hour_does_not_regenerate(db, network, stub_target):
    """The guard records the FIRE instant, so a retry, a restart mid-run or a
    manual scheduled-run inside the same hour is recognised exactly."""
    store = network["stores"]["SI1"]
    _set_cron(db, store, _cron_for_this_hour(0))
    _set_cron(db, network["stores"]["SI2"], _cron_for_this_hour(-2))
    _set_cron(db, network["stores"]["PR1"], _cron_for_this_hour(-2))

    first = outbound_svc.run_outbound_dispatch(db, TODAY)
    second = outbound_svc.run_outbound_dispatch(db, TODAY)

    assert first["stores_generated"] == 1
    assert second["stores_generated"] == 0
    assert second["skipped_already_run"] == 1
    assert len(stub_target) == 1          # nothing written outbound the second time


def test_respect_schedule_false_runs_every_store(db, network, stub_target):
    """"Run now" must act on everything — a button that silently does nothing
    because no store happens to be due in this hour looks broken."""
    for code in ("SI1", "SI2", "PR1"):
        _set_cron(db, network["stores"][code], _cron_for_this_hour(-2))

    result = outbound_svc.run_outbound_dispatch(db, TODAY, respect_schedule=False)

    assert result["respect_schedule"] is False
    assert result["stores_generated"] == 3
    assert result["stores_dispatched"] == 2          # the PR store is not dispatched
    assert result["skipped_not_due"] == 0


def test_manual_run_does_not_consume_the_schedule_guard(db, network, stub_target):
    """A manual run must not mark stores as having had their scheduled run —
    otherwise "Run now" silently cancels today's schedule."""
    store = network["stores"]["SI1"]
    _set_cron(db, store, _cron_for_this_hour(0))

    outbound_svc.run_outbound_dispatch(db, TODAY, respect_schedule=False)
    assert db.get(StoreSettings, store.id).last_indent_fire_at is None

    scheduled = outbound_svc.run_outbound_dispatch(db, TODAY)
    assert scheduled["stores_generated"] == 1


# ─────────────────────────────────────────────
# Purchase-request stores
# ─────────────────────────────────────────────
def test_purchase_request_store_is_generated_but_not_dispatched(db, network, stub_target):
    """The schedule governs GENERATION for every store; raising the request is
    the planner's action on the Purchase Request screen. Before schedules, such
    a store was skipped here entirely."""
    pr_store = network["stores"]["PR1"]
    _set_cron(db, pr_store, _cron_for_this_hour(0))
    _set_cron(db, network["stores"]["SI1"], _cron_for_this_hour(-2))
    _set_cron(db, network["stores"]["SI2"], _cron_for_this_hour(-2))

    result = outbound_svc.run_outbound_dispatch(db, TODAY)

    assert result["stores_generated"] == 1
    assert result["stores_dispatched"] == 0
    assert db.query(IndentReport).filter_by(store_id=pr_store.id).count() > 0
    assert db.query(OutboundDispatch).filter_by(store_id=pr_store.id).count() == 0
    assert stub_target == []
    ss = db.get(StoreSettings, pr_store.id)
    assert ss.last_indent_run_status == "generated"


# ─────────────────────────────────────────────
# Failure isolation and bookkeeping
# ─────────────────────────────────────────────
def test_one_store_failing_does_not_stop_the_others(db, network, stub_target, monkeypatch):
    bad, good = network["stores"]["SI1"], network["stores"]["SI2"]
    _set_cron(db, bad, _cron_for_this_hour(0))
    _set_cron(db, good, _cron_for_this_hour(0))
    _set_cron(db, network["stores"]["PR1"], _cron_for_this_hour(-2))

    real_generate = outbound_svc.generate_batch

    def flaky(db_, store_id, *args, **kwargs):
        if store_id == bad.id:
            raise RuntimeError("boom in store SI1")
        return real_generate(db_, store_id, *args, **kwargs)

    monkeypatch.setattr(outbound_svc, "generate_batch", flaky)

    result = outbound_svc.run_outbound_dispatch(db, TODAY)

    assert result["failed"] == 1
    assert result["stores_generated"] == 1
    assert result["stores_dispatched"] == 1
    assert db.query(IndentReport).filter_by(store_id=good.id).count() > 0

    failed_ss = db.get(StoreSettings, bad.id)
    assert failed_ss.last_indent_run_status == "failed"
    assert "boom in store SI1" in failed_ss.last_indent_error
    # The fire is recorded even on failure: no-catch-up means a failed store
    # waits for its next schedule rather than being retried every tick.
    assert failed_ss.last_indent_fire_at is not None


def test_dispatch_outcome_is_recorded_per_store(db, network, stub_target):
    store = network["stores"]["SI1"]
    _set_cron(db, store, _cron_for_this_hour(0))
    _set_cron(db, network["stores"]["SI2"], _cron_for_this_hour(-2))
    _set_cron(db, network["stores"]["PR1"], _cron_for_this_hour(-2))

    outbound_svc.run_outbound_dispatch(db, TODAY)

    ss = db.get(StoreSettings, store.id)
    assert ss.last_indent_run_status == "dispatched"
    assert ss.last_indent_error is None
    fire = sched.due_fire(_cron_for_this_hour(0), datetime.now(TZ))
    assert sched.is_same_fire(ss.last_indent_fire_at, fire)


# ─────────────────────────────────────────────
# Cost of an idle tick
# ─────────────────────────────────────────────
def test_idle_tick_does_not_build_the_item_cache(db, network, stub_target, monkeypatch):
    """This job went from daily to hourly, and most ticks have nothing due.
    ItemLevelCache loads every item and its settings, so building it on an idle
    tick would reintroduce the per-run DB load it exists to remove."""
    built = []
    real_cache = outbound_svc.ItemLevelCache

    def counting_cache(db_):
        built.append(1)
        return real_cache(db_)

    monkeypatch.setattr(outbound_svc, "ItemLevelCache", counting_cache)
    for code in ("SI1", "SI2", "PR1"):
        _set_cron(db, network["stores"][code], _cron_for_this_hour(-2))

    result = outbound_svc.run_outbound_dispatch(db, TODAY)

    assert result["skipped_not_due"] == 3
    assert built == []

    # ...and it IS built once when a store is due — one cache for the whole run.
    _set_cron(db, network["stores"]["SI1"], _cron_for_this_hour(0))
    _set_cron(db, network["stores"]["SI2"], _cron_for_this_hour(0))
    outbound_svc.run_outbound_dispatch(db, TODAY)
    assert len(built) == 1


def test_disabled_outbound_setting_short_circuits(db, network, stub_target):
    setting = outbound_svc.get_active_setting(db)
    setting.enabled = False
    db.commit()
    result = outbound_svc.run_outbound_dispatch(db, TODAY)
    assert result == {"skipped": True, "reason": "no_enabled_setting"}
