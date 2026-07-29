"""
APScheduler integration.
- One indent-generation job per store, interval = store's resolved indent_duration_days
- One FSN classification job per hospital, interval = hospital's fsn_schedule_days
- First run defaults to 'now' if no prior IndentReport/FSNClassification exists
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
import pytz

from app.config import settings

log = logging.getLogger("scheduler")

_scheduler: Optional[BackgroundScheduler] = None


def _local_tz():
    return pytz.timezone(settings.timezone)


def _make_scheduler() -> BackgroundScheduler:
    jobstores = {
        "default": SQLAlchemyJobStore(url=settings.database_url),
    }
    executors = {
        "default": ThreadPoolExecutor(max_workers=4),
    }
    return BackgroundScheduler(jobstores=jobstores, executors=executors, timezone=_local_tz())


def _run_indent_for_store(store_id: int) -> None:
    from app.db import SessionLocal
    from app.services.indent import generate_batch
    from app.models.indent import TriggerType

    db = SessionLocal()
    try:
        generate_batch(db, store_id, triggered_by=TriggerType.scheduler)
    finally:
        db.close()


def _run_fsn_for_hospital(hospital_id: int) -> None:
    from app.db import SessionLocal
    from app.services.fsn import compute_fsn_for_hospital

    db = SessionLocal()
    try:
        compute_fsn_for_hospital(db, hospital_id)
    finally:
        db.close()


def schedule_store_indent(store_id: int, interval_days: int) -> None:
    """Register or replace the indent job for a store."""
    global _scheduler
    if _scheduler is None:
        return
    job_id = f"indent_store_{store_id}"
    _scheduler.add_job(
        _run_indent_for_store,
        trigger="interval",
        days=interval_days,
        args=[store_id],
        id=job_id,
        replace_existing=True,
        next_run_time=_now_local(),
    )


def unschedule_store_indent(store_id: int) -> None:
    """Remove a store's indent job (no-op if it isn't registered)."""
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(f"indent_store_{store_id}")
        log.info("removed indent job for store %d", store_id)
    except Exception:
        pass


def sync_store_indent_job(db, store_id: int) -> bool:
    """Create or remove a store's indent job to match its resolved settings.

    The per-store job is OFF unless ``indent_scheduler_enabled`` resolves true
    (store setting, else hospital default). When the outbound pipeline is
    configured it generates the indents itself, so running this job as well
    would duplicate that work.

    Returns the resolved enabled flag.
    """
    from app.services import settings as settings_svc

    enabled = bool(settings_svc.resolve(db, 0, store_id, "indent_scheduler_enabled"))
    if enabled:
        interval = settings_svc.resolve(db, 0, store_id, "indent_duration_days")
        schedule_store_indent(store_id, int(interval or 30))
    else:
        unschedule_store_indent(store_id)
    return enabled


def sync_hospital_store_indent_jobs(db, hospital_id: int) -> None:
    """Re-evaluate every store in a hospital (its default may have changed)."""
    from app.models.store import Store

    for (sid,) in db.query(Store.id).filter(Store.hospital_id == hospital_id).all():
        sync_store_indent_job(db, sid)


def schedule_fsn_hospital(hospital_id: int, interval_days: int) -> None:
    """Register or replace the FSN job for a hospital."""
    global _scheduler
    if _scheduler is None:
        return
    job_id = f"fsn_hospital_{hospital_id}"
    _scheduler.add_job(
        _run_fsn_for_hospital,
        trigger="interval",
        days=interval_days,
        args=[hospital_id],
        id=job_id,
        replace_existing=True,
        next_run_time=_now_local(),
    )


def start_scheduler() -> None:
    """Start scheduler and register all existing stores and hospitals."""
    global _scheduler
    _scheduler = _make_scheduler()
    _scheduler.start()
    _register_all_jobs()
    register_all_data_mining_jobs()
    register_outbound_jobs()


def _register_all_jobs() -> None:
    from app.db import SessionLocal
    from app.models.store import Store
    from app.models.hospital import Hospital
    from app.services import settings as settings_svc

    db = SessionLocal()
    try:
        # Only stores that explicitly enable the scheduler get a job.
        enabled_ids = set()
        for store in db.query(Store).all():
            if sync_store_indent_job(db, store.id):
                enabled_ids.add(store.id)

        # The job store is persistent, so jobs survive restarts — including
        # jobs for stores that were since deleted or had the scheduler turned
        # off outside this process. Drop every indent job that should not
        # exist, so the setting is authoritative and deleted stores stop firing.
        for job in list(_scheduler.get_jobs()):
            if not job.id.startswith("indent_store_"):
                continue
            try:
                sid = int(job.id.rsplit("_", 1)[1])
            except (IndexError, ValueError):
                continue
            if sid not in enabled_ids:
                log.info("pruning stale indent job %s", job.id)
                unschedule_store_indent(sid)

        hospitals = db.query(Hospital).all()
        for hospital in hospitals:
            from app.models.settings import HospitalSettings
            hs = db.get(HospitalSettings, hospital.id)
            fsn_days = hs.fsn_schedule_days if hs else 30
            schedule_fsn_hospital(hospital.id, int(fsn_days))
    finally:
        db.close()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)


def _now_local() -> datetime:
    return datetime.now(_local_tz())


def run_job_now(job_id: str) -> bool:
    """Trigger a specific job to run immediately. Returns True if job found."""
    global _scheduler
    if _scheduler is None:
        return False
    job = _scheduler.get_job(job_id)
    if job is None:
        return False
    _scheduler.modify_job(job_id, next_run_time=_now_local())
    return True


def run_all_jobs_now() -> int:
    """Trigger all scheduler jobs to run immediately. Returns count triggered."""
    global _scheduler
    if _scheduler is None:
        return 0
    count = 0
    for job in _scheduler.get_jobs():
        _scheduler.modify_job(job.id, next_run_time=_now_local())
        count += 1
    return count


def get_scheduler_status() -> List[dict]:
    global _scheduler
    if _scheduler is None:
        return []
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "job_id": job.id,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return jobs


# ---------------------------------------------------------------------------
# Data mining scheduler integration
# ---------------------------------------------------------------------------

def _run_data_mining_config(config_id: int) -> None:
    from app.db import SessionLocal
    from app.services.data_mining import run_mining_config

    db = SessionLocal()
    try:
        run_mining_config(config_id, db)
    finally:
        db.close()


def schedule_data_mining_config(config_id: int, cron: str) -> None:
    """Register or replace a cron job for a data mining config."""
    global _scheduler
    if _scheduler is None:
        return
    # cron format: "min hour dom mon dow"  e.g. "0 2 * * *"
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError(
            f"schedule_cron must be a 5-field cron expression, got: {cron!r}"
        )
    minute, hour, day, month, day_of_week = parts
    job_id = f"datamining_{config_id}"
    _scheduler.add_job(
        _run_data_mining_config,
        trigger="cron",
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        args=[config_id],
        id=job_id,
        replace_existing=True,
    )


def unschedule_data_mining_config(config_id: int) -> None:
    """Remove the cron job for a data mining config (if it exists)."""
    global _scheduler
    if _scheduler is None:
        return
    job_id = f"datamining_{config_id}"
    try:
        _scheduler.remove_job(job_id)
    except Exception:
        pass  # job may not exist


def _next_fire_after(cron: str, reference: datetime) -> Optional[datetime]:
    """
    Return the first scheduled cron fire strictly after `reference`.
    Cron expression is interpreted in the configured local timezone.
    Returns None if the cron expression cannot be parsed.
    """
    try:
        trigger = CronTrigger.from_crontab(cron, timezone=_local_tz())
    except Exception:
        return None
    if reference.tzinfo is None:
        reference = _local_tz().localize(reference)
    return trigger.get_next_fire_time(reference, reference)


def _has_missed_fire(config, now: datetime) -> bool:
    """
    Quartz-style misfire check: was a scheduled cron fire due while the app was
    down (or has the config never run past its first scheduled fire)?

    Baseline is the config's last successful trigger (`last_run_at`), falling
    back to its creation time for a config that has never run.
    """
    reference = config.last_run_at or config.created_at
    next_due = _next_fire_after(config.schedule_cron, reference)
    return next_due is not None and next_due <= now


def register_all_data_mining_jobs() -> None:
    """
    Called at startup to register cron jobs for all enabled mining configs.

    For each config, also performs a Quartz-style misfire catch-up: if a
    scheduled fire was due while the app was offline, the job is triggered to
    run immediately (once), then resumes its normal cron cadence.
    """
    from app.db import SessionLocal
    from app.models.data_mining import DataMiningConfig
    from app.services.data_mining import reset_orphaned_runs

    now = _now_local()
    db = SessionLocal()
    try:
        # Clear runs left in 'running' by a prior crash/restart so the
        # "already running" guard can't block configs indefinitely.
        reset_orphaned_runs(db)
        configs = (
            db.query(DataMiningConfig)
            .filter(
                DataMiningConfig.enabled.is_(True),
                DataMiningConfig.schedule_cron.isnot(None),
            )
            .all()
        )
        for config in configs:
            try:
                schedule_data_mining_config(config.id, config.schedule_cron)
            except Exception:
                log.warning(
                    "[config=%d name=%r] Bad cron %r — skipping at boot",
                    config.id, config.name, config.schedule_cron,
                )
                continue  # bad cron expression — skip catch-up too

            if _has_missed_fire(config, now):
                job_id = f"datamining_{config.id}"
                log.info(
                    "[config=%d name=%r] Missed scheduled fire while offline "
                    "(last_run_at=%s) — triggering catch-up run now",
                    config.id, config.name, config.last_run_at,
                )
                _scheduler.modify_job(job_id, next_run_time=now)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Outbound dispatch + Kafka outbox publisher
# ---------------------------------------------------------------------------

OUTBOUND_DISPATCH_JOB_ID = "outbound_dispatch"
OUTBOX_PUBLISHER_JOB_ID = "outbox_publisher"


def _run_outbound_dispatch() -> None:
    from app.db import SessionLocal
    from app.services.outbound import run_outbound_dispatch

    db = SessionLocal()
    try:
        run_outbound_dispatch(db)
    finally:
        db.close()


def _run_outbox_publisher() -> None:
    from app.db import SessionLocal
    from app.services.outbound import publish_outbox

    db = SessionLocal()
    try:
        publish_outbox(db)
    finally:
        db.close()


def schedule_outbound_dispatch(cron: str) -> None:
    """Register/replace the network-wide outbound dispatch cron job."""
    global _scheduler
    if _scheduler is None or not cron:
        return
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError(f"schedule_cron must be a 5-field cron expression, got: {cron!r}")
    minute, hour, day, month, dow = parts
    _scheduler.add_job(
        _run_outbound_dispatch, trigger="cron",
        minute=minute, hour=hour, day=day, month=month, day_of_week=dow,
        id=OUTBOUND_DISPATCH_JOB_ID, replace_existing=True,
    )


def unschedule_outbound_dispatch() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(OUTBOUND_DISPATCH_JOB_ID)
    except Exception:
        pass


def schedule_outbox_publisher(interval_seconds: int = 60) -> None:
    """Register the outbox publisher — a short-interval poll that drains the
    Kafka outbox. Idempotent; safe to call repeatedly."""
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.add_job(
        _run_outbox_publisher, trigger="interval", seconds=interval_seconds,
        id=OUTBOX_PUBLISHER_JOB_ID, replace_existing=True, next_run_time=_now_local(),
    )


def register_outbound_jobs() -> None:
    """At startup: register the outbox publisher and, if an enabled outbound
    setting has a cron, the dispatch job."""
    from app.db import SessionLocal
    from app.services.outbound import get_active_setting

    schedule_outbox_publisher()
    db = SessionLocal()
    try:
        setting = get_active_setting(db)
        if setting and setting.enabled and setting.schedule_cron:
            try:
                schedule_outbound_dispatch(setting.schedule_cron)
            except Exception:
                log.warning("Bad outbound schedule_cron %r — skipping at boot", setting.schedule_cron)
    finally:
        db.close()
