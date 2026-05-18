"""
FSN Classification service — schedule-based.
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import func, tuple_

from app.models.consumption import ConsumptionRecord
from app.models.classification import FSNClassification, FSNClass
from app.models.item import Item
from app.models.store import Store
from app.models.settings import HospitalSettings


def compute_fsn_for_hospital(db: Session, hospital_id: int) -> dict:
    hospital_s = db.get(HospitalSettings, hospital_id)
    period_days = hospital_s.fsn_period_days if hospital_s else 365
    fast_threshold = hospital_s.fsn_fast_threshold if hospital_s else 1.0
    slow_threshold = hospital_s.fsn_slow_threshold if hospital_s else 0.1

    stores = db.query(Store).filter(Store.hospital_id == hospital_id).all()
    store_ids = [s.id for s in stores]
    if not store_ids:
        return {"hospital_id": hospital_id, "records_updated": 0}

    items = db.query(Item.id).all()
    item_ids = [i.id for i in items]
    if not item_ids:
        return {"hospital_id": hospital_id, "records_updated": 0}

    as_of = date.today()
    cutoff = as_of - timedelta(days=period_days)

    # ONE query: get all (item_id, store_id) → total_qty for this hospital
    rows = (
        db.query(
            ConsumptionRecord.item_id,
            ConsumptionRecord.store_id,
            func.sum(ConsumptionRecord.quantity).label("total"),
        )
        .filter(
            ConsumptionRecord.store_id.in_(store_ids),
            ConsumptionRecord.date >= cutoff,
            ConsumptionRecord.date <= as_of,
        )
        .group_by(ConsumptionRecord.item_id, ConsumptionRecord.store_id)
        .all()
    )
    totals: dict[tuple, float] = {(r.item_id, r.store_id): float(r.total) for r in rows}

    # ONE query: fetch all existing FSN records for these stores
    existing_records = (
        db.query(FSNClassification)
        .filter(FSNClassification.store_id.in_(store_ids))
        .all()
    )
    existing_map: dict[tuple, FSNClassification] = {
        (r.item_id, r.store_id): r for r in existing_records
    }

    new_records = []
    updated = 0
    for store_id in store_ids:
        for item_id in item_ids:
            total_qty = totals.get((item_id, store_id), 0.0)
            avg_daily = total_qty / period_days if period_days > 0 else 0.0

            if avg_daily > fast_threshold:
                cls = FSNClass.F
            elif avg_daily < slow_threshold:
                cls = FSNClass.N
            else:
                cls = FSNClass.S

            existing = existing_map.get((item_id, store_id))
            if existing:
                existing.classification = cls
                existing.avg_daily_consumption = Decimal(str(round(avg_daily, 4)))
                existing.period_days = period_days
            else:
                new_records.append(FSNClassification(
                    item_id=item_id,
                    store_id=store_id,
                    classification=cls,
                    avg_daily_consumption=Decimal(str(round(avg_daily, 4))),
                    period_days=period_days,
                ))
            updated += 1

    if new_records:
        db.add_all(new_records)
    db.commit()
    return {"hospital_id": hospital_id, "records_updated": updated}
