"""
APScheduler integration.
- One indent-generation job per store, interval = store's resolved indent_duration_days
- One FSN classification job per hospital, interval = hospital's fsn_schedule_days
- First run defaults to 'now' if no prior IndentReport/FSNClassification exists
"""
from datetime import datetime, timezone
from typing import Optional, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from app.config import settings

_scheduler: Optional[BackgroundScheduler] = None


def _make_scheduler() -> BackgroundScheduler:
    jobstores = {
        "default": SQLAlchemyJobStore(url=settings.database_url),
    }
    executors = {
        "default": ThreadPoolExecutor(max_workers=4),
    }
    return BackgroundScheduler(jobstores=jobstores, executors=executors, timezone="UTC")


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
        next_run_time=datetime.now(timezone.utc),  # default to now on first setup
    )


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
        next_run_time=datetime.now(timezone.utc),
    )


def start_scheduler() -> None:
    """Start scheduler and register all existing stores and hospitals."""
    global _scheduler
    _scheduler = _make_scheduler()
    _scheduler.start()
    _register_all_jobs()
    register_all_data_mining_jobs()


def _register_all_jobs() -> None:
    from app.db import SessionLocal
    from app.models.store import Store
    from app.models.hospital import Hospital
    from app.services import settings as settings_svc

    db = SessionLocal()
    try:
        stores = db.query(Store).all()
        for store in stores:
            interval = settings_svc.resolve(db, 0, store.id, "indent_duration_days")
            schedule_store_indent(store.id, int(interval or 30))

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


def run_job_now(job_id: str) -> bool:
    """Trigger a specific job to run immediately. Returns True if job found."""
    global _scheduler
    if _scheduler is None:
        return False
    job = _scheduler.get_job(job_id)
    if job is None:
        return False
    _scheduler.modify_job(job_id, next_run_time=datetime.now(timezone.utc))
    return True


def run_all_jobs_now() -> int:
    """Trigger all scheduler jobs to run immediately. Returns count triggered."""
    global _scheduler
    if _scheduler is None:
        return 0
    count = 0
    for job in _scheduler.get_jobs():
        _scheduler.modify_job(job.id, next_run_time=datetime.now(timezone.utc))
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


def register_all_data_mining_jobs() -> None:
    """Called at startup to register cron jobs for all enabled mining configs."""
    from app.db import SessionLocal
    from app.models.data_mining import DataMiningConfig

    db = SessionLocal()
    try:
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
                pass  # bad cron expression — skip silently at boot
    finally:
        db.close()
