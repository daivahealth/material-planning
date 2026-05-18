"""
Indent projection service.
Generates IndentReport records for (item, store) pairs.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.consumption import ConsumptionRecord, ClosingStock, OpenIndent
from app.models.indent import IndentReport, TriggerType
from app.models.surge import SurgeRecord, get_season
from app.services import settings as settings_svc
from app.services.formula import (
    STANDARD_FORMULA,
    evaluate_formula,
)


def _avg_daily(db: Session, item_id: int, store_id: int,
               lookback_days: int, as_of: date) -> float:
    cutoff = as_of - timedelta(days=lookback_days)
    result = db.query(func.sum(ConsumptionRecord.quantity)).filter(
        ConsumptionRecord.item_id == item_id,
        ConsumptionRecord.store_id == store_id,
        ConsumptionRecord.date >= cutoff,
        ConsumptionRecord.date <= as_of,
    ).scalar()
    total = float(result or 0)
    return total / lookback_days if lookback_days > 0 else 0.0


def _latest_closing_stock(db: Session, item_id: int, store_id: int,
                           as_of: date) -> float:
    record = (
        db.query(ClosingStock)
        .filter(
            ClosingStock.item_id == item_id,
            ClosingStock.store_id == store_id,
            ClosingStock.date <= as_of,
        )
        .order_by(ClosingStock.date.desc())
        .first()
    )
    return float(record.quantity) if record else 0.0


def _open_indent_qty(db: Session, item_id: int, store_id: int, as_of: date) -> float:
    """Sum of all open (pending) indent quantities for item/store as of the given date."""
    result = db.query(func.sum(OpenIndent.quantity)).filter(
        OpenIndent.item_id == item_id,
        OpenIndent.store_id == store_id,
        OpenIndent.as_of_date <= as_of,
    ).scalar()
    return float(result or 0)


def _surge_extra(db: Session, item_id: int, store_id: int, target_month: int) -> float:
    season = get_season(target_month)
    records = db.query(SurgeRecord).filter(
        SurgeRecord.item_id == item_id,
        SurgeRecord.store_id == store_id,
        (SurgeRecord.month == target_month) | (SurgeRecord.season == season),
    ).all()
    if not records:
        return 0.0
    return float(sum(r.extra_qty for r in records)) / len(records)


def generate_indent(
    db: Session,
    item_id: int,
    store_id: int,
    as_of: Optional[date] = None,
    triggered_by: TriggerType = TriggerType.api,
) -> IndentReport:
    if as_of is None:
        as_of = date.today()

    report = _build_indent_report(db, item_id, store_id, as_of, triggered_by)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _build_indent_report(
    db: Session,
    item_id: int,
    store_id: int,
    as_of: date,
    triggered_by: TriggerType,
) -> IndentReport:
    """Calculate and construct an IndentReport without committing."""
    s = settings_svc.resolve_all(db, item_id, store_id)
    lookback_days: int = s["lookback_days"]
    indent_days: int = s["indent_duration_days"]
    safety_pct: float = s["safety_stock_pct"]
    formula_type: str = s["projection_formula"]
    formula_expr: Optional[str] = s["projection_formula_expr"]

    avg_daily = _avg_daily(db, item_id, store_id, lookback_days, as_of)
    closing_stock = _latest_closing_stock(db, item_id, store_id, as_of)
    open_qty = _open_indent_qty(db, item_id, store_id, as_of)
    projected_need = avg_daily * indent_days
    safety_stock = projected_need * safety_pct

    if formula_type == "custom" and formula_expr:
        raw = evaluate_formula(formula_expr, avg_daily, indent_days, closing_stock, safety_pct, open_qty)
        base_indent = max(0.0, raw)
        formula_used = formula_expr
    else:
        raw = projected_need + safety_stock - closing_stock - open_qty
        base_indent = max(0.0, raw)
        formula_used = STANDARD_FORMULA

    target_month = (as_of + timedelta(days=1)).month  # indent is for NEXT period
    surge_qty = _surge_extra(db, item_id, store_id, target_month)
    total_indent = base_indent + surge_qty

    period_start = as_of + timedelta(days=1)
    period_end = as_of + timedelta(days=indent_days)

    report = IndentReport(
        item_id=item_id,
        store_id=store_id,
        period_start=period_start,
        period_end=period_end,
        avg_daily_consumption=Decimal(str(round(avg_daily, 4))),
        projected_need=Decimal(str(round(projected_need, 4))),
        closing_stock_qty=Decimal(str(round(closing_stock, 4))),
        safety_stock_qty=Decimal(str(round(safety_stock, 4))),
        base_indent_qty=Decimal(str(round(base_indent, 4))),
        surge_indent_qty=Decimal(str(round(surge_qty, 4))),
        open_indent_qty=Decimal(str(round(open_qty, 4))),
        total_indent_qty=Decimal(str(round(total_indent, 4))),
        formula_used=formula_used,
        triggered_by=triggered_by,
    )
    return report


def generate_batch(
    db: Session,
    store_id: int,
    as_of: Optional[date] = None,
    triggered_by: TriggerType = TriggerType.api,
) -> tuple:
    """
    Generate indent reports for all items that have closing stock entries
    for the given store. Returns (reports, skipped_count).
    """
    # Only generate for items that have been tracked (have closing stock) at this store
    item_ids = [
        row[0] for row in
        db.query(ClosingStock.item_id)
        .filter(ClosingStock.store_id == store_id)
        .distinct()
        .all()
    ]
    if as_of is None:
        as_of = date.today()
    reports = []
    skipped = 0
    for item_id in item_ids:
        try:
            r = _build_indent_report(db, item_id, store_id, as_of, triggered_by)
            reports.append(r)
        except Exception:
            skipped += 1
    if reports:
        db.add_all(reports)
        db.commit()
    return reports, skipped
