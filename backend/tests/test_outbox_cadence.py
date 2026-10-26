"""
Adaptive cadence of the Kafka outbox publisher.

While events remain unpublished the job must come back after
``outbox_retry_seconds``; once the backlog clears it must fall back to its own
``outbox_poll_seconds`` interval without any trigger swapping.

These run a REAL BackgroundScheduler (memory jobstore) because the behaviour
under test is APScheduler's: whether modify_job(next_run_time=...) called from
inside the job's own execution survives the scheduler updating next_run_time
when that job completes.
"""
import time
from datetime import datetime

import pytest
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

from app import scheduler as sched
from app.config import settings
from app.services import outbound as outbound_svc

IDLE = 300
RETRY = 60


@pytest.fixture
def live_scheduler(monkeypatch):
    """A real scheduler with an in-memory jobstore, wired into the module."""
    s = BackgroundScheduler(
        executors={"default": ThreadPoolExecutor(max_workers=2)},
        timezone=sched._local_tz(),
    )
    s.start()
    monkeypatch.setattr(sched, "_scheduler", s)
    monkeypatch.setattr(settings, "outbox_poll_seconds", IDLE, raising=False)
    monkeypatch.setattr(settings, "outbox_retry_seconds", RETRY, raising=False)
    yield s
    s.shutdown(wait=False)


def _stub_outbox(monkeypatch, backlog: int):
    """publish_outbox is a no-op; the backlog it leaves behind is the variable."""
    calls = []
    monkeypatch.setattr(outbound_svc, "publish_outbox",
                        lambda db, **kw: calls.append("published") or {"published": 0})
    monkeypatch.setattr(outbound_svc, "unpublished_outbox_count", lambda db: backlog)
    return calls


def _seconds_until_next_run(job) -> float:
    now = datetime.now(sched._local_tz())
    return (job.next_run_time - now).total_seconds()


def _wait_for_first_fire(calls, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if calls:
            return True
        time.sleep(0.05)
    return False


def test_backlog_pulls_next_run_forward_to_retry_interval(live_scheduler, monkeypatch):
    calls = _stub_outbox(monkeypatch, backlog=3)
    sched.schedule_outbox_publisher()          # idle interval = 300s, fires immediately

    assert _wait_for_first_fire(calls), "publisher job never ran"
    time.sleep(0.4)                            # let modify_job land in the jobstore

    job = live_scheduler.get_job(sched.OUTBOX_PUBLISHER_JOB_ID)
    delta = _seconds_until_next_run(job)
    assert RETRY - 10 < delta < RETRY + 10, (
        f"expected next run in ~{RETRY}s while backlog remains, got {delta:.1f}s "
        "(modify_job from inside the running job did not stick)"
    )


def test_empty_backlog_falls_back_to_idle_interval(live_scheduler, monkeypatch):
    calls = _stub_outbox(monkeypatch, backlog=0)
    sched.schedule_outbox_publisher()

    assert _wait_for_first_fire(calls), "publisher job never ran"
    time.sleep(0.4)

    job = live_scheduler.get_job(sched.OUTBOX_PUBLISHER_JOB_ID)
    delta = _seconds_until_next_run(job)
    assert IDLE - 15 < delta < IDLE + 15, (
        f"expected fallback to the ~{IDLE}s idle interval, got {delta:.1f}s"
    )


def test_retry_cadence_repeats_while_backlog_persists(live_scheduler, monkeypatch):
    """A second run with work still pending must schedule another fast retry,
    i.e. the fast cadence is sustained, not a one-shot."""
    calls = _stub_outbox(monkeypatch, backlog=1)
    sched.schedule_outbox_publisher()
    assert _wait_for_first_fire(calls)
    time.sleep(0.3)

    for _ in range(3):
        sched._scheduler.modify_job(sched.OUTBOX_PUBLISHER_JOB_ID,
                                    next_run_time=sched._now_local())
        time.sleep(0.4)
        job = live_scheduler.get_job(sched.OUTBOX_PUBLISHER_JOB_ID)
        delta = _seconds_until_next_run(job)
        assert RETRY - 10 < delta < RETRY + 10, f"cadence slipped to {delta:.1f}s"

    assert len(calls) >= 4


def test_reschedule_is_safe_when_job_is_gone(live_scheduler):
    """Shutdown racing a run must not raise out of the job."""
    sched._retry_outbox_publisher_soon(5)      # job was never registered
