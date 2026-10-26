"""
CSV export of Item × Store settings.

The contract that matters is ROUND-TRIP: the exported file must re-import
unchanged, which means the columns match the importer's and — critically —
an unset override exports as a BLANK, not 0/false. A literal 0 would pin the
value and stop it inheriting, silently changing planning on re-import.
"""
import csv
import io

import pytest

from app.models.hospital import Hospital
from app.models.store import Store
from app.models.item import Item
from app.models.settings import ItemStoreSettings
from app.services.csv_import import (
    ITEM_STORE_CSV_COLUMNS,
    ITEM_STORE_SETTING_TYPES,
    import_item_store_settings,
)


def _seed(db):
    h = Hospital(code="H1", name="H")
    db.add(h)
    db.flush()
    s1 = Store(hospital_id=h.id, code="ST-A", name="A")
    s2 = Store(hospital_id=h.id, code="ST-B", name="B")
    i1 = Item(code="IT-1", name="One", unit="Ea")
    i2 = Item(code="IT-2", name="Two", unit="Ea")
    db.add_all([s1, s2, i1, i2])
    db.flush()

    # fully populated
    db.add(ItemStoreSettings(
        item_id=i1.id, store_id=s1.id, indent_duration_days=21,
        safety_stock_days=2.5, reorder_level=500.0, min_stock=800.0,
        max_stock=9000.0, min_order_qty=1000.0, pack_size=25,
        planning_enabled=False,
    ))
    # sparse: only one override set; everything else must export blank
    db.add(ItemStoreSettings(item_id=i2.id, store_id=s2.id, pack_size=7))
    # an explicit True, to prove it is not confused with "unset"
    db.add(ItemStoreSettings(item_id=i1.id, store_id=s2.id, planning_enabled=True))
    db.flush()
    return {"s1": s1, "s2": s2, "i1": i1, "i2": i2}


def _export(db, **params) -> str:
    """Call the endpoint function directly and drain the streamed CSV.

    StreamingResponse exposes an ASYNC body_iterator even when handed a plain
    sync iterator, so it has to be consumed through the event loop.
    """
    import asyncio
    from app.api.settings import export_item_store_settings

    resp = export_item_store_settings(db=db, current_user=None, **params)

    async def _drain():
        chunks = []
        async for chunk in resp.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode())
        return b"".join(chunks)

    return asyncio.run(_drain()).decode()


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_header_matches_the_importer_exactly(db):
    _seed(db)
    reader = csv.reader(io.StringIO(_export(db, store_id=None, item_id=None)))
    assert next(reader) == list(ITEM_STORE_CSV_COLUMNS)


def test_unset_overrides_export_blank_not_zero(db):
    ids = _seed(db)
    rows = {(r["item_code"], r["store_code"]): r
            for r in _rows(_export(db, store_id=None, item_id=None))}

    sparse = rows[("IT-2", "ST-B")]
    assert sparse["pack_size"] == "7"
    for field in ITEM_STORE_SETTING_TYPES:
        if field == "pack_size":
            continue
        assert sparse[field] == "", (
            f"{field} was unset but exported as {sparse[field]!r}; a 0/false here "
            "would stop the value inheriting on re-import"
        )


def test_booleans_distinguish_false_true_and_unset(db):
    _seed(db)
    rows = {(r["item_code"], r["store_code"]): r
            for r in _rows(_export(db, store_id=None, item_id=None))}
    assert rows[("IT-1", "ST-A")]["planning_enabled"] == "false"
    assert rows[("IT-1", "ST-B")]["planning_enabled"] == "true"
    assert rows[("IT-2", "ST-B")]["planning_enabled"] == ""


def test_whole_numbers_have_no_trailing_decimal(db):
    _seed(db)
    rows = {(r["item_code"], r["store_code"]): r
            for r in _rows(_export(db, store_id=None, item_id=None))}
    full = rows[("IT-1", "ST-A")]
    assert full["reorder_level"] == "500"       # not "500.0"
    assert full["safety_stock_days"] == "2.5"   # genuine decimal preserved
    assert full["indent_duration_days"] == "21"
    assert full["pack_size"] == "25"


def test_only_configured_rows_are_exported(db):
    _seed(db)
    rows = _rows(_export(db, store_id=None, item_id=None))
    # 2 stores x 2 items = 4 combinations, but only 3 have overrides
    assert len(rows) == 3


def test_filters_narrow_the_export(db):
    ids = _seed(db)
    only_store = _rows(_export(db, store_id=ids["s1"].id, item_id=None))
    assert {r["store_code"] for r in only_store} == {"ST-A"}

    only_item = _rows(_export(db, store_id=None, item_id=ids["i2"].id))
    assert {r["item_code"] for r in only_item} == {"IT-2"}


def test_export_reimports_unchanged(db):
    """The round-trip contract: wipe the rows, re-import the file, same values."""
    ids = _seed(db)
    exported = _export(db, store_id=None, item_id=None)

    before = {}
    for row in db.query(ItemStoreSettings).all():
        before[(row.item_id, row.store_id)] = {
            f: getattr(row, f) for f in ITEM_STORE_SETTING_TYPES
        }

    db.query(ItemStoreSettings).delete(synchronize_session=False)
    db.flush()
    # synchronize_session=False leaves the deleted rows in the identity map, so
    # the importer's db.get() would hand back stale in-memory objects. A real
    # import runs in its own request session; expunge to match that.
    db.expunge_all()
    assert db.query(ItemStoreSettings).count() == 0

    result = import_item_store_settings(db, io.BytesIO(exported.encode()))
    assert not result["errors"], result["errors"]
    assert result["imported"] == 3

    after = {}
    for row in db.query(ItemStoreSettings).all():
        after[(row.item_id, row.store_id)] = {
            f: getattr(row, f) for f in ITEM_STORE_SETTING_TYPES
        }

    assert after == before


def test_blank_cells_do_not_clear_values_set_after_the_export(db):
    """Documents the limit of the round-trip.

    The importer treats a blank cell as "leave unchanged" (only the literal
    token NULL clears a field). So re-importing an export reproduces the
    exported state onto a CLEAN slate, but it does not revert overrides added
    afterwards. That is the non-destructive choice — a partially filled sheet
    can never wipe configuration — not an oversight.
    """
    ids = _seed(db)
    exported = _export(db, item_id=ids["i2"].id, store_id=ids["s2"].id)
    row = _rows(exported)[0]
    assert row["pack_size"] == "7" and row["min_stock"] == ""

    # someone sets min_stock in the UI after the export was taken
    live = db.get(ItemStoreSettings, (ids["i2"].id, ids["s2"].id))
    live.min_stock = 250.0
    db.flush()
    db.expunge_all()

    result = import_item_store_settings(db, io.BytesIO(exported.encode()))
    assert not result["errors"], result["errors"]

    live = db.get(ItemStoreSettings, (ids["i2"].id, ids["s2"].id))
    assert live.pack_size == 7
    assert live.min_stock == 250.0, (
        "a blank cell must not clear a value — use the literal NULL token for that"
    )


def test_null_token_in_an_edited_export_clears_the_override(db):
    """The documented way to remove an override from an exported sheet."""
    ids = _seed(db)
    exported = _export(db, item_id=ids["i1"].id, store_id=ids["s1"].id)
    edited = exported.replace(",25,", ",NULL,")      # pack_size 25 -> NULL
    assert "NULL" in edited
    db.expunge_all()

    result = import_item_store_settings(db, io.BytesIO(edited.encode()))
    assert not result["errors"], result["errors"]

    live = db.get(ItemStoreSettings, (ids["i1"].id, ids["s1"].id))
    assert live.pack_size is None
    assert live.indent_duration_days == 21          # untouched
