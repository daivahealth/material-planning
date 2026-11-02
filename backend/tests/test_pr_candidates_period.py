"""
PR candidates default to the store's CURRENT plan.

Regeneration replaces only the period it generates, so running on a new date
leaves earlier periods behind. Returning all of them meant an item restocked
above its target still showed a positive quantity from a superseded plan, and
with ~1.5-2.5k lines per period the 5000-row cap was consumed by stale rows.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.purchase_requests import list_candidates, list_candidate_periods
from app.models.hospital import Hospital
from app.models.store import Store
from app.models.item import Item
from app.models.indent import IndentReport, TriggerType
from app.models.settings import StoreSettings
from app.models.user import User, UserRole

P1 = date(2026, 4, 1)
P2 = date(2026, 5, 1)


@pytest.fixture
def pr_store(db):
    h = Hospital(code="H1", name="H")
    db.add(h)
    db.flush()
    st = Store(hospital_id=h.id, code="PR1", name="PR Store")
    db.add(st)
    db.flush()
    db.add(StoreSettings(store_id=st.id, request_type="purchase_request"))
    items = [Item(code=f"I{n}", name=f"Item {n}", unit="Ea") for n in range(4)]
    db.add_all(items)
    db.flush()

    def line(item, period, qty, pr_done=False):
        return IndentReport(
            item_id=item.id, store_id=st.id,
            period_start=period, period_end=period + timedelta(days=29),
            avg_daily_consumption=Decimal("1"), projected_need=Decimal("30"),
            closing_stock_qty=Decimal("0"), safety_stock_qty=Decimal("3"),
            base_indent_qty=Decimal(str(qty)), surge_indent_qty=Decimal("0"),
            open_indent_qty=Decimal("0"), total_indent_qty=Decimal(str(qty)),
            triggered_by=TriggerType.api, pr_initiated=pr_done,
        )

    # old plan: two eligible lines that are now obsolete
    db.add(line(items[0], P1, 280))
    db.add(line(items[1], P1, 140))
    # current plan: one eligible, one already PR'd, one zero (restocked)
    db.add(line(items[0], P2, 55))
    db.add(line(items[1], P2, 90, pr_done=True))
    db.add(line(items[2], P2, 0))
    db.flush()

    admin = User(username="adm", hashed_password="x", role=UserRole.master)
    db.add(admin)
    db.flush()
    return st, items, admin


def test_candidates_default_to_the_newest_period_only(db, pr_store):
    st, items, admin = pr_store
    rows = list_candidates(store_id=st.id, period_start=None, supplier_id=None,
                           current_user=admin, db=db)
    assert {r.period_start for r in rows} == {P2}, "superseded periods must not be offered"
    # within the current plan: the PR'd line and the zero-qty line are excluded
    assert [(r.item_code, float(r.total_indent_qty)) for r in rows] == [("I0", 55.0)]


def test_an_explicit_period_is_still_honoured(db, pr_store):
    st, items, admin = pr_store
    rows = list_candidates(store_id=st.id, period_start=P1, supplier_id=None,
                           current_user=admin, db=db)
    assert {r.period_start for r in rows} == {P1}
    assert len(rows) == 2


def test_periods_endpoint_lists_newest_first_with_eligible_counts(db, pr_store):
    st, items, admin = pr_store
    periods = list_candidate_periods(store_id=st.id, current_user=admin, db=db)
    assert [p.period_start for p in periods] == [P2, P1]
    assert [p.is_current for p in periods] == [True, False]
    # P2 has 3 lines but only 1 eligible; P1 has 2 eligible
    assert [p.line_count for p in periods] == [1, 2]


def test_restocked_item_disappears_once_the_new_plan_is_generated(db, pr_store):
    """The reported symptom: stock above target must stop offering the item."""
    st, items, admin = pr_store
    before = list_candidates(store_id=st.id, period_start=P1, supplier_id=None,
                             current_user=admin, db=db)
    assert any(r.item_code == "I1" and float(r.total_indent_qty) > 0 for r in before)

    current = list_candidates(store_id=st.id, period_start=None, supplier_id=None,
                              current_user=admin, db=db)
    assert not any(r.item_code == "I2" for r in current), "zero-qty line must not be offered"


def test_store_with_no_reports_returns_empty_not_an_error(db, pr_store):
    st, items, admin = pr_store
    db.query(IndentReport).filter(IndentReport.store_id == st.id).delete(synchronize_session=False)
    db.flush()
    assert list_candidates(store_id=st.id, period_start=None, supplier_id=None,
                           current_user=admin, db=db) == []
    assert list_candidate_periods(store_id=st.id, current_user=admin, db=db) == []


def test_non_pr_store_is_still_rejected(db, pr_store):
    st, items, admin = pr_store
    db.query(StoreSettings).filter(StoreSettings.store_id == st.id).update(
        {"request_type": "stock_indent"}, synchronize_session=False)
    db.flush()
    with pytest.raises(HTTPException) as exc:
        list_candidates(store_id=st.id, period_start=None, supplier_id=None,
                        current_user=admin, db=db)
    assert exc.value.status_code == 400
