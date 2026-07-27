"""Outbound pipeline API — singleton settings, connection test, manual run, dispatch log."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.outbound import OutboundSetting, OutboundDispatch, DbType
from app.models.user import User
from app.schemas.outbound import (
    OutboundSettingUpsert, OutboundSettingOut, OutboundDispatchOut, ConnectionTestResult,
)
from app.services.auth import get_current_user, require_master
from app.services.data_mining import encrypt_password, get_source_engine
from app.services.outbound import get_active_setting, run_outbound_dispatch

log = logging.getLogger("outbound")

router = APIRouter(
    prefix="/api/outbound",
    tags=["Outbound"],
    dependencies=[Depends(get_current_user)],
)

_DEFAULT_MAPPING = {f: f for f in
                    ["item_code", "store_code", "qty", "request_number",
                     "request_type", "inserted_date", "request_status"]}


def _to_out(obj: OutboundSetting) -> OutboundSettingOut:
    return OutboundSettingOut(
        id=obj.id, enabled=obj.enabled, db_type=obj.db_type.value,
        host=obj.host, port=obj.port, database_name=obj.database_name, username=obj.username,
        has_password=bool(obj.encrypted_password), target_table=obj.target_table,
        column_mapping=obj.column_mapping or {}, request_status_value=obj.request_status_value,
        request_type_value=getattr(obj, "request_type_value", None) or "StockIndent",
        schedule_cron=obj.schedule_cron, kafka_brokers=obj.kafka_brokers, kafka_topic=obj.kafka_topic,
        last_run_at=obj.last_run_at, last_run_status=obj.last_run_status, last_error=obj.last_error,
    )


@router.get("/settings", response_model=OutboundSettingOut)
def get_settings(db: Session = Depends(get_db)):
    obj = get_active_setting(db)
    if obj is None:
        raise HTTPException(404, "Outbound settings not configured")
    return _to_out(obj)


@router.put("/settings", response_model=OutboundSettingOut)
def upsert_settings(
    payload: OutboundSettingUpsert,
    _: User = Depends(require_master),
    db: Session = Depends(get_db),
):
    obj = get_active_setting(db)
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)

    if obj is None:
        obj = OutboundSetting(column_mapping=dict(_DEFAULT_MAPPING))
        db.add(obj)
    for k, v in data.items():
        setattr(obj, k, v)
    if password:
        obj.encrypted_password = encrypt_password(password)
    if not obj.column_mapping:
        obj.column_mapping = dict(_DEFAULT_MAPPING)
    db.commit()
    db.refresh(obj)

    # (Re)schedule the dispatch cron to match the saved setting.
    from app.scheduler import schedule_outbound_dispatch, unschedule_outbound_dispatch
    if obj.enabled and obj.schedule_cron:
        try:
            schedule_outbound_dispatch(obj.schedule_cron)
        except Exception as exc:
            log.warning("could not schedule outbound dispatch: %s", exc)
    else:
        unschedule_outbound_dispatch()
    return _to_out(obj)


@router.post("/settings/test", response_model=ConnectionTestResult)
def test_connection(_: User = Depends(require_master), db: Session = Depends(get_db)):
    obj = get_active_setting(db)
    if obj is None or not obj.encrypted_password:
        raise HTTPException(400, "Configure and save connection details first")
    try:
        engine = get_source_engine(obj)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return ConnectionTestResult(success=True)
    except Exception as exc:
        return ConnectionTestResult(success=False, error=str(exc)[:500])


@router.post("/run")
def run_now(_: User = Depends(require_master), db: Session = Depends(get_db)):
    """Trigger the dispatch immediately (synchronous)."""
    result = run_outbound_dispatch(db)
    return result


@router.get("/dispatches", response_model=list[OutboundDispatchOut])
def list_dispatches(
    store_id: int | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    q = db.query(OutboundDispatch)
    if store_id:
        q = q.filter(OutboundDispatch.store_id == store_id)
    return q.order_by(OutboundDispatch.created_at.desc()).limit(min(limit, 2000)).all()
