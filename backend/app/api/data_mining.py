import threading
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.models.data_mining import DataMiningConfig, DataMiningRun, RunStatus
from app.models.user import User
from app.schemas.data_mining import (
    DataMiningConfigCreate,
    DataMiningConfigOut,
    DataMiningConfigUpdate,
    DataMiningRunOut,
    DataMiningStatusOut,
    DataMiningTestResult,
)
from app.services.auth import get_current_user, require_master
from app.services.data_mining import (
    encrypt_password,
    run_mining_config,
    test_connection,
)

router = APIRouter(
    prefix="/data-mining",
    tags=["data-mining"],
    dependencies=[Depends(get_current_user)],
)


def _get_config_or_404(config_id: int, db: Session) -> DataMiningConfig:
    config = db.get(DataMiningConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="DataMiningConfig not found")
    return config


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("/configs", response_model=List[DataMiningConfigOut])
def list_configs(db: Session = Depends(get_db)):
    return db.query(DataMiningConfig).order_by(DataMiningConfig.name).all()


@router.post(
    "/configs",
    response_model=DataMiningConfigOut,
    status_code=status.HTTP_201_CREATED,
)
def create_config(
    payload: DataMiningConfigCreate,
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude={"password"})
    data["encrypted_password"] = encrypt_password(payload.password)
    config = DataMiningConfig(**data)
    db.add(config)
    db.commit()
    db.refresh(config)

    if config.schedule_cron and config.enabled:
        _register_job(config.id, config.schedule_cron)

    return config


@router.get("/configs/{config_id}", response_model=DataMiningConfigOut)
def get_config(config_id: int, db: Session = Depends(get_db)):
    return _get_config_or_404(config_id, db)


@router.put("/configs/{config_id}", response_model=DataMiningConfigOut)
def update_config(
    config_id: int,
    payload: DataMiningConfigUpdate,
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    config = _get_config_or_404(config_id, db)
    update_data = payload.model_dump(exclude_none=True)

    if "password" in update_data:
        config.encrypted_password = encrypt_password(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(config, field, value)

    db.commit()
    db.refresh(config)

    # Re-register scheduler job if cron or enabled changed
    if "schedule_cron" in update_data or "enabled" in update_data:
        from app import scheduler as scheduler_svc
        if config.schedule_cron and config.enabled:
            scheduler_svc.schedule_data_mining_config(config.id, config.schedule_cron)
        else:
            scheduler_svc.unschedule_data_mining_config(config.id)

    return config


@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(
    config_id: int,
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    config = _get_config_or_404(config_id, db)
    from app import scheduler as scheduler_svc
    scheduler_svc.unschedule_data_mining_config(config_id)
    db.delete(config)
    db.commit()


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

@router.post("/configs/{config_id}/test", response_model=DataMiningTestResult)
def test_config_connection(
    config_id: int,
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    config = _get_config_or_404(config_id, db)
    result = test_connection(config)
    return DataMiningTestResult(**result)


# ---------------------------------------------------------------------------
# Manual run (fire-and-forget in a background thread)
# ---------------------------------------------------------------------------

def _run_in_thread(config_id: int) -> None:
    db = SessionLocal()
    try:
        run_mining_config(config_id, db)
    finally:
        db.close()


@router.post(
    "/configs/{config_id}/run",
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_run(
    config_id: int,
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    config = _get_config_or_404(config_id, db)
    if config.last_run_status == RunStatus.running:
        raise HTTPException(
            status_code=409,
            detail="This config is already running. Wait for it to complete.",
        )
    thread = threading.Thread(
        target=_run_in_thread, args=(config_id,), daemon=True
    )
    thread.start()
    return {"detail": "Mining run started."}


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------

@router.get(
    "/configs/{config_id}/runs",
    response_model=List[DataMiningRunOut],
)
def list_runs(
    config_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    _get_config_or_404(config_id, db)
    return (
        db.query(DataMiningRun)
        .filter(DataMiningRun.config_id == config_id)
        .order_by(DataMiningRun.started_at.desc())
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Status overview
# ---------------------------------------------------------------------------

@router.get("/status", response_model=List[DataMiningStatusOut])
def get_status(db: Session = Depends(get_db)):
    configs = db.query(DataMiningConfig).order_by(DataMiningConfig.name).all()
    result = []
    for config in configs:
        latest_run = (
            db.query(DataMiningRun)
            .filter(DataMiningRun.config_id == config.id)
            .order_by(DataMiningRun.started_at.desc())
            .first()
        )
        result.append(
            DataMiningStatusOut(
                config=DataMiningConfigOut.model_validate(config),
                latest_run=DataMiningRunOut.model_validate(latest_run)
                if latest_run
                else None,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Internal helper (used by create/update to schedule without importing at module level)
# ---------------------------------------------------------------------------

def _register_job(config_id: int, cron: str) -> None:
    try:
        from app import scheduler as scheduler_svc
        scheduler_svc.schedule_data_mining_config(config_id, cron)
    except Exception:
        pass  # scheduler may not be started yet (e.g. during tests)
