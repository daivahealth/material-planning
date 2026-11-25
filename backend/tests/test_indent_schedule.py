"""
Store-wise indent schedule (issue #15).

The schedule is data, evaluated once an hour by the outbound dispatch run. The
behaviour worth pinning down is therefore not "does a job exist" but:

  * resolution  — store override beats the hospital default, and every store
                  resolves to something;
  * the window  — exactly one tick wide, so a missed fire is SKIPPED rather
                  than caught up;
  * rounding    — a non-zero minute is acted on by the following hourly tick;
  * validation  — an expression that fires twice a day is rejected, because the
                  second dispatch of a day is a silent no-op;
  * the guard   — the same fire is never acted on twice.
"""
from datetime import datetime, timedelta

import pytest
import pytz

from app.models.hospital import Hospital
from app.models.settings import HospitalSettings, StoreSettings
from app.models.store import Store
from app.schemas.settings import HospitalSettingsCreate, StoreSettingsCreate
from app.services import indent_schedule as sched

TZ = pytz.timezone("Asia/Kolkata")


def at(y, m, d, hh, mm=0):
    return TZ.localize(datetime(y, m, d, hh, mm))


@pytest.fixture
def two_stores(db):
    """One store inheriting the hospital schedule, one overriding it."""
    h = Hospital(code="H1", name="H")
    db.add(h)
    db.flush()
    db.add(HospitalSettings(hospital_id=h.id, indent_schedule_cron="0 6 * * *"))
    inherit = Store(hospital_id=h.id, code="S-INH", name="Inheriting")
    override = Store(hospital_id=h.id, code="S-OVR", name="Overriding")
    db.add_all([inherit, override])
    db.flush()
    db.add(StoreSettings(store_id=override.id, indent_schedule_cron="0 9 * * MON"))
    db.flush()
    return {"hospital": h, "inherit": inherit, "override": override}


# ─────────────────────────────────────────────
# Resolution
# ─────────────────────────────────────────────
def test_store_override_beats_hospital_default(db, two_stores):
    cron, source = sched.resolve_store_cron(db, two_stores["override"].id)
    assert (cron, source) == ("0 9 * * MON", sched.SOURCE_STORE)


def test_store_without_override_inherits_hospital(db, two_stores):
    cron, source = sched.resolve_store_cron(db, two_stores["inherit"].id)
    assert (cron, source) == ("0 6 * * *", sched.SOURCE_HOSPITAL)


def test_blank_store_override_inherits(db, two_stores):
    """A blank string is not an override — it is how the UI clears one."""
    ss = db.get(StoreSettings, two_stores["override"].id)
    ss.indent_schedule_cron = "   "
    db.flush()
    cron, source = sched.resolve_store_cron(db, two_stores["override"].id)
    assert (cron, source) == ("0 6 * * *", sched.SOURCE_HOSPITAL)


def test_missing_hospital_settings_row_falls_back_to_default(db):
    """Defensive: a hospital that has never been saved has no settings row.
    The store must still resolve to a schedule — one evaluation path, no
    'unconfigured' branch in the dispatch loop."""
    h = Hospital(code="H2", name="No settings")
    db.add(h)
    db.flush()
    store = Store(hospital_id=h.id, code="S9", name="Orphan")
    db.add(store)
    db.flush()
    cron, source = sched.resolve_store_cron(db, store.id)
    assert (cron, source) == (sched.DEFAULT_INDENT_CRON, sched.SOURCE_DEFAULT)


def test_load_store_crons_matches_per_store_resolution(db, two_stores):
    """The batch loader is what the dispatch loop uses; it must agree with the
    single-store resolver or 200 stores get planned on a different schedule
    from the one the UI shows."""
    bulk = sched.load_store_crons(db)
    for store in (two_stores["inherit"], two_stores["override"]):
        assert bulk[store.id] == sched.resolve_store_cron(db, store.id)


# ─────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────
@pytest.mark.parametrize("cron", ["0 6 * * *", "0 6 * * MON,WED,FRI", "30 22 * * SUN",
                                  "0 6 1 * *"])
def test_valid_crons_accepted(cron):
    assert sched.validate_cron(cron) == cron


@pytest.mark.parametrize("bad,reason", [
    ("", "5-field"),
    ("0 6 * *", "5 fields"),
    ("0 6 * * FUNDAY", "not a valid cron"),
    ("99 6 * * *", "not a valid cron"),
])
def test_malformed_crons_rejected(bad, reason):
    with pytest.raises(ValueError) as exc:
        sched.validate_cron(bad)
    assert reason.lower() in str(exc.value).lower()


@pytest.mark.parametrize("bad", ["0 6,18 * * *", "*/30 6 * * *", "0 * * * *",
                                 "0,30 6 * * *", "0 6-9 * * *"])
def test_more_than_one_fire_per_day_rejected(bad):
    """dispatch_store is idempotent on (store, period_start) and period_start
    is derived from the DATE, so a second fire the same day dispatches nothing.
    Rejected at entry rather than silently half-working."""
    with pytest.raises(ValueError) as exc:
        sched.validate_cron(bad)
    assert "once a day" in str(exc.value)


def test_hospital_schema_rejects_blank_cron():
    """Mandatory at the hospital level — it is the default every store falls
    back to, so there must always be one."""
    with pytest.raises(ValueError) as exc:
        HospitalSettingsCreate(indent_schedule_cron="  ")
    assert "required at the hospital level" in str(exc.value)


def test_hospital_schema_accepts_absent_cron():
    """Absent means 'not being changed' — the API sends only set fields."""
    assert HospitalSettingsCreate().indent_schedule_cron is None


def test_store_schema_normalises_blank_to_none():
    """At store level a blank box means 'inherit', so it must clear the column
    rather than store an empty string that resolution would have to special-case."""
    assert StoreSettingsCreate(indent_schedule_cron="").indent_schedule_cron is None


def test_store_schema_rejects_twice_daily():
    with pytest.raises(ValueError) as exc:
        StoreSettingsCreate(indent_schedule_cron="0 6,18 * * *")
    assert "once a day" in str(exc.value)


# ─────────────────────────────────────────────
# Due detection: the one-hour window
# ─────────────────────────────────────────────
def test_due_in_its_own_hour():
    fire = sched.due_fire("0 6 * * *", at(2026, 11, 24, 6))
    assert fire == at(2026, 11, 24, 6)


def test_not_due_in_the_next_hour():
    assert sched.due_fire("0 6 * * *", at(2026, 11, 24, 7)) is None


def test_non_zero_minute_is_acted_on_by_the_following_tick():
    """06:30 falls in the window (06:00, 07:00] that the 07:00 run examines,
    so the configured minute is effectively rounded up to the next hour."""
    assert sched.due_fire("30 6 * * *", at(2026, 11, 24, 6)) is None
    assert sched.due_fire("30 6 * * *", at(2026, 11, 24, 7)) == at(2026, 11, 24, 6, 30)


def test_window_is_half_open_so_a_fire_is_not_counted_twice():
    """A fire exactly on the lower boundary belongs to the previous tick.

    Shown with a wider window so the boundary is the only thing under test:
    at 08:00 with a 2-hour window the examined range is (06:00, 08:00], and a
    06:00 fire sits on the excluded edge.
    """
    assert sched.due_fire("0 6 * * *", at(2026, 11, 24, 8), window_hours=2) is None
    assert sched.due_fire("0 7 * * *", at(2026, 11, 24, 8), window_hours=2) is not None


def test_day_of_week_schedule_only_fires_on_those_days():
    monday = at(2026, 11, 23, 9)      # 2026-11-23 is a Monday
    tuesday = at(2026, 11, 24, 9)
    assert sched.due_fire("0 9 * * MON", monday) == monday
    assert sched.due_fire("0 9 * * MON", tuesday) is None


def test_missed_fires_are_skipped_not_caught_up():
    """Down from 06:00 to 11:07: the 11:00-ish tick examines only the hour just
    elapsed, so nothing older is replayed — the agreed no-catch-up behaviour,
    and it falls out of the window width rather than needing its own logic."""
    assert sched.due_fire("0 6 * * *", at(2026, 11, 24, 11, 7)) is None


def test_five_hour_gap_runs_once_for_the_current_hour_only():
    """An hourly schedule after a 5-hour outage: only the current hour's fire
    is due, not the five that were missed."""
    now = at(2026, 11, 24, 11)
    # Hourly is not a legal store schedule, so evaluate the daily one at each
    # of the hours that were missed: exactly one of them is due.
    due = [h for h in range(6, 12) if sched.due_fire("0 11 * * *", at(2026, 11, 24, h))]
    assert due == [11]
    assert sched.due_fire("0 11 * * *", now) == now


def test_unparseable_cron_is_never_due():
    """A bad expression must not be treated as 'fires always' — that would
    regenerate the store on every tick."""
    assert sched.due_fire("nonsense", at(2026, 11, 24, 6)) is None


def test_naive_now_is_localised():
    """The dispatch loop passes an aware 'now', but a caller passing naive must
    not get a TypeError comparing it to an aware fire time."""
    assert sched.due_fire("0 6 * * *", datetime(2026, 11, 24, 6)) is not None


# ─────────────────────────────────────────────
# Double-run guard
# ─────────────────────────────────────────────
def test_same_fire_is_recognised_across_naive_storage():
    """SQLite drops the offset Postgres keeps; comparing naive to aware raises,
    which would turn the guard into a crash."""
    fire = at(2026, 11, 24, 6)
    assert sched.is_same_fire(fire, fire)
    assert sched.is_same_fire(fire.replace(tzinfo=None), fire)
    assert not sched.is_same_fire(fire - timedelta(hours=1), fire)
    assert not sched.is_same_fire(None, fire)


def test_record_store_run_creates_the_row_if_absent(db, two_stores):
    """A store with no settings row still has to be able to record its run, or
    the guard silently does nothing for exactly the stores that use defaults."""
    store_id = two_stores["inherit"].id
    assert db.get(StoreSettings, store_id) is None
    fire = at(2026, 11, 24, 6)
    sched.record_store_run(db, store_id, fire, "dispatched")
    ss = db.get(StoreSettings, store_id)
    assert sched.is_same_fire(ss.last_indent_fire_at, fire)
    assert ss.last_indent_run_status == "dispatched"
    assert ss.last_indent_error is None


def test_record_store_run_truncates_a_long_error(db, two_stores):
    sched.record_store_run(db, two_stores["override"].id, None, "failed", "x" * 5000)
    ss = db.get(StoreSettings, two_stores["override"].id)
    assert len(ss.last_indent_error) == 1000


# ─────────────────────────────────────────────
# Presentation helpers (the UI shows these, so they are behaviour)
# ─────────────────────────────────────────────
@pytest.mark.parametrize("cron,expected", [
    ("0 6 * * *", "Runs daily at 06:00"),
    ("0 9 * * MON,WED,FRI", "Runs Mon, Wed, Fri at 09:00"),
    ("0 7 * * 1-5", "Runs Mon-Fri at 07:00"),
    ("0 6,18 * * *", "Invalid schedule"),
])
def test_describe(cron, expected):
    assert sched.describe(cron) == expected


def test_effective_hour_reports_the_round_up():
    assert sched.effective_hour("0 6 * * *") == 6
    assert sched.effective_hour("30 6 * * *") == 7
    assert sched.effective_hour("30 23 * * *") == 0      # rolls into the next day
    assert sched.effective_hour("bad cron") is None


def test_ceil_to_tick_is_the_instant_the_store_really_runs():
    assert sched.ceil_to_tick(at(2026, 11, 24, 6)) == at(2026, 11, 24, 6)
    assert sched.ceil_to_tick(at(2026, 11, 24, 6, 30)) == at(2026, 11, 24, 7)
    # Monday 23:30 is acted on at 00:00 on TUESDAY — the day shifts too.
    assert sched.ceil_to_tick(at(2026, 11, 23, 23, 30)) == at(2026, 11, 24, 0)


def test_next_fire_times_are_strictly_increasing():
    fires = sched.next_fire_times("0 6 * * MON", 3, after=at(2026, 11, 24, 12))
    assert len(fires) == 3
    assert fires == sorted(fires)
    assert all(f.hour == 6 and f.weekday() == 0 for f in fires)


@pytest.mark.parametrize("cron,hourly", [
    ("0 * * * *", True),
    ("*/15 * * * *", True),
    ("0 */2 * * *", True),          # every 2h — the hour field still steps
    ("50 14 * * *", False),         # today's production value
    ("0 6,18 * * *", False),
    ("", False),
    (None, False),
])
def test_outbound_cron_hourly_detection(cron, hourly):
    """Store schedules are only evaluated when outbound dispatch runs, so this
    check is what turns a silent misconfiguration into a visible warning."""
    assert sched.outbound_cron_is_hourly(cron) is hourly


# ─────────────────────────────────────────────
# API surface
# ─────────────────────────────────────────────
def test_preview_endpoint_reports_the_round_up():
    """The UI renders this instead of parsing cron in the browser — one
    implementation of the rules, so the preview cannot disagree with the job."""
    from app.api.settings import preview_indent_schedule

    out = preview_indent_schedule("30 6 * * *")
    assert out["valid"] is True
    assert out["rounded_up"] is True
    assert out["effective_hour"] == 7
    assert out["description"] == "Runs daily at 06:30"
    assert len(out["run_times"]) == 3
    # run_times are the instants the store is really generated, fire_times the
    # cron's own fires — they differ precisely when the minute is non-zero.
    assert out["run_times"] != out["fire_times"]
    assert all(t.endswith(":00:00+05:30") for t in out["run_times"])


def test_preview_endpoint_reports_an_invalid_cron_without_raising():
    from app.api.settings import preview_indent_schedule

    out = preview_indent_schedule("0 6,18 * * *")
    assert out["valid"] is False
    assert "once a day" in out["error"]


def test_store_schedule_listing_shows_source_and_last_run(db, two_stores):
    from app.api.settings import list_store_indent_schedules
    from app.models.user import User, UserRole

    admin = User(username="adm", hashed_password="x", role=UserRole.master)
    db.add(admin)
    db.flush()
    sched.record_store_run(db, two_stores["override"].id, at(2026, 11, 23, 9), "dispatched")

    out = list_store_indent_schedules(current_user=admin, db=db)
    rows = {r["store_code"]: r for r in out["stores"]}

    assert rows["S-INH"]["source"] == sched.SOURCE_HOSPITAL
    assert rows["S-INH"]["cron"] == "0 6 * * *"
    assert rows["S-OVR"]["source"] == sched.SOURCE_STORE
    assert rows["S-OVR"]["description"] == "Runs Mon at 09:00"
    assert rows["S-OVR"]["last_indent_run_status"] == "dispatched"
    assert rows["S-INH"]["last_indent_fire_at"] is None


def test_store_schedule_listing_warns_when_outbound_is_not_hourly(db, two_stores):
    """The one deployment step that cannot be done in code: left at a daily
    cron, every store schedule is silently ignored."""
    from app.api.settings import list_store_indent_schedules
    from app.models.outbound import DbType, OutboundSetting
    from app.models.user import User, UserRole

    admin = User(username="adm", hashed_password="x", role=UserRole.master)
    db.add(admin)
    db.add(OutboundSetting(
        enabled=True, db_type=DbType.postgresql, target_table="t",
        schedule_cron="50 14 * * *",
    ))
    db.flush()

    out = list_store_indent_schedules(current_user=admin, db=db)
    assert out["outbound"]["hourly"] is False
    assert "0 * * * *" in out["outbound"]["warning"]

    db.query(OutboundSetting).first().schedule_cron = "0 * * * *"
    db.flush()
    out = list_store_indent_schedules(current_user=admin, db=db)
    assert out["outbound"]["hourly"] is True
    assert out["outbound"]["warning"] is None


def test_csv_import_sets_a_store_schedule(db, two_stores):
    """200 stores will not be configured one at a time in the UI, so the CSV
    path has to carry the field — and reject a bad one per row."""
    import io

    from app.services.csv_import import import_store_settings

    csv_bytes = io.BytesIO(
        b"store_code,indent_schedule_cron\n"
        b"S-INH,0 7 * * MON\n"
        b"S-OVR,0 6-9 * * *\n"
    )
    result = import_store_settings(db, csv_bytes)

    assert result["imported"] == 1
    assert len(result["errors"]) == 1
    assert "once a day" in result["errors"][0]["message"]
    assert db.get(StoreSettings, two_stores["inherit"].id).indent_schedule_cron == "0 7 * * MON"
    # the rejected row left the existing override untouched
    assert db.get(StoreSettings, two_stores["override"].id).indent_schedule_cron == "0 9 * * MON"


def test_csv_import_clears_an_override_with_the_null_token(db, two_stores):
    import io

    from app.services.csv_import import import_store_settings

    result = import_store_settings(
        db, io.BytesIO(b"store_code,indent_schedule_cron\nS-OVR,NULL\n")
    )
    assert result["imported"] == 1
    assert db.get(StoreSettings, two_stores["override"].id).indent_schedule_cron is None
    assert sched.resolve_store_cron(db, two_stores["override"].id) == (
        "0 6 * * *", sched.SOURCE_HOSPITAL,
    )
