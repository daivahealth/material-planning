"""
Consumption analysis endpoint.
Returns daily series, bucket averages, and all supported demand estimates
(baseline, weighted rolling, trend-adjusted) for a chosen item/store/window.
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.item import Item
from app.models.store import Store
from app.models.hospital import Hospital
from app.models.consumption import ClosingStock, OpenIndent
from app.models.user import User
from app.services import settings as settings_svc
from app.services.auth import get_current_user
from app.services.access import assert_store_access
from app.services.indent import (
    _avg_daily,
    _open_indent_qty,
    _daily_series,
    _weighted_rolling_avg,
    _trend_adjusted_avg,
)

router = APIRouter(
    prefix="/api/consumption",
    tags=["Consumption"],
    dependencies=[Depends(get_current_user)],
)


# ---------- response schemas ----------

class DayPoint(BaseModel):
    date: date
    quantity: float


class BucketPoint(BaseModel):
    bucket_index: int       # 0 = oldest
    start_date: date
    end_date: date
    total: float
    avg_daily: float
    weight: float           # weight applied in weighted rolling calc


class ConsumptionAnalysisOut(BaseModel):
    item_id: int
    store_id: int
    item_code: str
    item_name: str
    store_code: str
    store_name: str
    hospital_name: str
    as_of: date
    lookback_days: int
    # effective settings used
    rolling_bucket_days: int
    rolling_recent_weight_factor: float
    trend_min_points: int
    # demand estimates
    baseline_avg_daily: float
    weighted_rolling_avg_daily: float
    trend_adjusted_avg_daily: float
    # latest closing stock on/before as_of (0 / None if never recorded)
    closing_stock_qty: float
    closing_stock_date: Optional[date] = None
    # quantity already ordered but not yet received, from the latest snapshot
    open_indent_qty: float = 0.0
    open_indent_date: Optional[date] = None
    # aggregate stats
    total_consumption: float
    active_days: int        # days with qty > 0
    # series data
    daily_series: List[DayPoint]
    bucket_series: List[BucketPoint]


# ---------- endpoint ----------

@router.get("/analysis", response_model=ConsumptionAnalysisOut)
def consumption_analysis(
    item_id: int,
    store_id: int,
    as_of: Optional[date] = Query(None, description="Reference date (defaults to today)"),
    lookback_days: Optional[int] = Query(None, ge=1, description="Override lookback window (defaults to hospital setting)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_store_access(db, current_user, store_id)
    if as_of is None:
        as_of = date.today()

    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    hospital = db.get(Hospital, store.hospital_id)

    s = settings_svc.resolve_all(db, item_id, store_id)
    effective_lookback = lookback_days if lookback_days is not None else s["lookback_days"]
    bucket_days: int = s["rolling_bucket_days"]
    weight_factor: float = s["rolling_recent_weight_factor"]
    trend_min_points: int = s["trend_min_points"]

    # --- demand estimates ---
    baseline = _avg_daily(db, item_id, store_id, effective_lookback, as_of)
    weighted = _weighted_rolling_avg(
        db, item_id, store_id, effective_lookback, bucket_days, weight_factor, as_of
    )
    trend = _trend_adjusted_avg(
        db, item_id, store_id, effective_lookback, trend_min_points, as_of
    )

    # --- daily series ---
    raw_series = _daily_series(db, item_id, store_id, effective_lookback, as_of)
    start_day = as_of - timedelta(days=effective_lookback - 1)
    daily: List[DayPoint] = [
        DayPoint(date=start_day + timedelta(days=i), quantity=v)
        for i, v in enumerate(raw_series)
    ]

    total_consumption = sum(d.quantity for d in daily)
    active_days = sum(1 for d in daily if d.quantity > 0)

    # --- latest closing stock on/before as_of ---
    cs = (
        db.query(ClosingStock)
        .filter(
            ClosingStock.item_id == item_id,
            ClosingStock.store_id == store_id,
            ClosingStock.date <= as_of,
        )
        .order_by(ClosingStock.date.desc())
        .first()
    )
    closing_stock_qty = float(cs.quantity) if cs else 0.0
    closing_stock_date = cs.date if cs else None

    # --- open indents (stock on order) ---
    # Reuses the indent service's helper so this matches exactly what the
    # calculation subtracts: only the latest snapshot date is counted, never a
    # sum across historical imports.
    open_indent_qty = _open_indent_qty(db, item_id, store_id, as_of)
    open_indent_date = (
        db.query(func.max(OpenIndent.as_of_date))
        .filter(
            OpenIndent.item_id == item_id,
            OpenIndent.store_id == store_id,
            OpenIndent.as_of_date <= as_of,
        )
        .scalar()
    )

    # --- bucket series (mirrors _weighted_rolling_avg grouping exactly) ---
    n_full = len(raw_series) // bucket_days
    buckets: List[BucketPoint] = []
    if n_full >= 1:
        trimmed = raw_series[len(raw_series) - n_full * bucket_days:]
        trimmed_start = start_day + timedelta(days=len(raw_series) - n_full * bucket_days)

        # same linear ramp as _weighted_rolling_avg
        if n_full == 1:
            weights_list = [1.0]
        else:
            step = (weight_factor - 1.0) / (n_full - 1)
            weights_list = [1.0 + step * i for i in range(n_full)]

        for i in range(n_full):
            slice_ = trimmed[i * bucket_days:(i + 1) * bucket_days]
            b_total = sum(slice_)
            b_avg = b_total / bucket_days
            b_start = trimmed_start + timedelta(days=i * bucket_days)
            b_end = b_start + timedelta(days=bucket_days - 1)
            buckets.append(BucketPoint(
                bucket_index=i,
                start_date=b_start,
                end_date=b_end,
                total=round(b_total, 4),
                avg_daily=round(b_avg, 4),
                weight=round(weights_list[i], 4),
            ))

    return ConsumptionAnalysisOut(
        item_id=item_id,
        store_id=store_id,
        item_code=item.code,
        item_name=item.name,
        store_code=store.code,
        store_name=store.name,
        hospital_name=hospital.name if hospital else "",
        as_of=as_of,
        lookback_days=effective_lookback,
        rolling_bucket_days=bucket_days,
        rolling_recent_weight_factor=weight_factor,
        trend_min_points=trend_min_points,
        baseline_avg_daily=round(baseline, 6),
        weighted_rolling_avg_daily=round(weighted, 6),
        trend_adjusted_avg_daily=round(trend, 6),
        closing_stock_qty=round(closing_stock_qty, 4),
        closing_stock_date=closing_stock_date,
        open_indent_qty=round(open_indent_qty, 4),
        open_indent_date=open_indent_date,
        total_consumption=round(total_consumption, 4),
        active_days=active_days,
        daily_series=daily,
        bucket_series=buckets,
    )
