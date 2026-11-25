"""
Store-wise indent schedule (issue #15).

Each store resolves to a 5-field cron expression saying when its indents should
be generated: ``StoreSettings.indent_schedule_cron`` when set, otherwise the
mandatory ``HospitalSettings.indent_schedule_cron``.

The expression is **data, evaluated on every outbound dispatch run** — it is
never registered as an APScheduler job. That is deliberate, and is what makes
this different from the legacy per-store ``indent_store_*`` jobs:

  * saving a store's settings cannot re-anchor its schedule to "now";
  * a deleted store leaves nothing firing behind it;
  * the persistent jobstore is untouched, whatever anyone configures.

How "due" is decided
--------------------
The outbound dispatch job runs **hourly** (``0 * * * *``) and asks one question
per store: *did this store's cron fire inside the hour just elapsed?* — the
half-open window ``(now - 1h, now]``.

Because the window is only one tick wide, a fire older than that is never
considered, so **missed runs are skipped rather than caught up** (the agreed
behaviour) with no extra bookkeeping. Down from 06:00 to 11:07? The 11:00 run
examines ``(10:07, 11:07]`` only.

Consequences, both surfaced in the UI rather than left to be discovered:

  * only the **hour** field is effectively honoured — ``30 6 * * *`` fires at
    06:30, which lands in the window examined by the 07:00 run, so it runs at
    07:00. :func:`effective_hour` reports that.
  * ``dispatch_store`` is idempotent on ``(store_id, period_start)`` and
    ``period_start = as_of + 1 day``, so two runs on the same calendar day
    dispatch **once**. :func:`validate_cron` therefore rejects an expression
    that fires more than once a day, instead of letting the second fire be a
    silent no-op.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import pytz
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.models.settings import HospitalSettings, StoreSettings
from app.models.store import Store

log = logging.getLogger("indent_schedule")

#: Fallback when a store's hospital has no settings row at all. The hospital
#: column is NOT NULL with this same server default, so in practice this is
#: reached only for a hospital that has never been saved.
DEFAULT_INDENT_CRON = "0 6 * * *"

#: How often the outbound dispatch job must run for schedules to be honoured.
#: The due-detection window is exactly this wide, so a less frequent outbound
#: cron silently drops schedules — see :func:`outbound_cron_is_hourly`.
TICK_HOURS = 1

#: Resolution sources, highest priority first.
SOURCE_STORE = "store"
SOURCE_HOSPITAL = "hospital"
SOURCE_DEFAULT = "default"

_SINGLE_VALUE_RE = re.compile(r"^\d{1,2}$")


def _local_tz():
    return pytz.timezone(app_settings.timezone)


def _aware(moment: datetime) -> datetime:
    """Localise a naive datetime; pass an aware one through unchanged."""
    if moment.tzinfo is None:
        return _local_tz().localize(moment)
    return moment


# ─────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────
def validate_cron(expr: str) -> str:
    """Validate an indent-schedule cron and return it stripped.

    Raises ``ValueError`` with a message meant for the user. Beyond "is this a
    cron expression", one rule is enforced: **at most one fire per day**.

    That rule exists because ``dispatch_store`` keys on
    ``(store_id, period_start)`` with ``period_start = as_of + 1 day``, so a
    second fire on the same calendar day computes the same period and dispatches
    nothing. Rather than let ``0 6,18 * * *`` look configured while half of it
    does nothing, it is rejected at the point of entry. Equivalent to requiring
    the minute and hour fields to name a single value each — any ``*``, list,
    range or step in those two fields produces repeats within a day.
    """
    raw = (expr or "").strip()
    if not raw:
        raise ValueError("indent_schedule_cron must be a 5-field cron expression")
    parts = raw.split()
    if len(parts) != 5:
        raise ValueError(
            "indent_schedule_cron must have 5 fields "
            "(minute hour day-of-month month day-of-week), "
            f"got {len(parts)}: {raw!r}"
        )
    try:
        CronTrigger.from_crontab(raw, timezone=_local_tz())
    except Exception as exc:
        raise ValueError(f"indent_schedule_cron is not a valid cron expression: {exc}") from exc

    minute, hour = parts[0], parts[1]
    for label, field in (("minute", minute), ("hour", hour)):
        if not _SINGLE_VALUE_RE.match(field):
            raise ValueError(
                f"indent_schedule_cron may fire at most once a day, so the {label} "
                f"field must be a single value, not {field!r}. Indents dispatch once "
                "per store per day (the request is keyed on the period, not the hour), "
                "so a second fire the same day would do nothing. Use the day-of-week "
                "field for less frequent schedules, e.g. '0 6 * * MON,WED,FRI'."
            )
    return raw


_DAY_NAMES = {
    "0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed", "4": "Thu", "5": "Fri",
    "6": "Sat", "7": "Sun",
    "SUN": "Sun", "MON": "Mon", "TUE": "Tue", "WED": "Wed", "THU": "Thu",
    "FRI": "Fri", "SAT": "Sat",
}


def _describe_days(dow: str) -> str:
    """'MON,WED,FRI' -> 'Mon, Wed, Fri'; '1-5' -> 'Mon-Fri'. Falls back to the
    raw field for anything exotic rather than guessing."""
    tokens = [t.strip().upper() for t in dow.split(",") if t.strip()]
    names = []
    for tok in tokens:
        if tok in _DAY_NAMES:
            names.append(_DAY_NAMES[tok])
        elif "-" in tok:
            lo, _, hi = tok.partition("-")
            if lo in _DAY_NAMES and hi in _DAY_NAMES:
                names.append(f"{_DAY_NAMES[lo]}-{_DAY_NAMES[hi]}")
            else:
                return dow
        else:
            return dow
    return ", ".join(names) or dow


def describe(cron: str) -> str:
    """Short human-readable rendering of an indent schedule, for the UI."""
    try:
        validate_cron(cron)
    except ValueError:
        return "Invalid schedule"
    minute, hour, dom, month, dow = cron.strip().split()
    at = f"{int(hour):02d}:{int(minute):02d}"
    if month == "*" and dom == "*":
        when = "daily" if dow == "*" else _describe_days(dow)
    elif month == "*" and dow == "*":
        when = f"on day {dom} of the month"
    else:
        when = f"on cron {dom} {month} {dow}"
    return f"Runs {when} at {at}"


def ceil_to_tick(moment: datetime) -> datetime:
    """The hourly tick that will act on a fire at ``moment``.

    A fire at 06:30 is inside the window examined by the 07:00 run, so that is
    when the store is actually generated. Exposed so the UI can show the real
    run instants — which also makes the late-evening case visible, where
    ``30 23 * * MON`` is acted on at 00:00 on **Tuesday**.
    """
    moment = _aware(moment)
    if (moment.minute, moment.second, moment.microsecond) == (0, 0, 0):
        return moment
    naive = (moment.replace(tzinfo=None) + timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )
    return _local_tz().localize(naive)


def effective_hour(cron: str) -> Optional[int]:
    """The hour a schedule will actually run in, or None if unparseable.

    The due-detection window is one hour wide and the outbound job fires on the
    hour, so a fire at ``HH:MM`` with ``MM > 0`` is acted on by the ``HH+1``
    run. Surfacing this is the difference between a documented rounding rule and
    a bug report.
    """
    try:
        validate_cron(cron)
    except ValueError:
        return None
    minute, hour = cron.strip().split()[:2]
    return (int(hour) + 1) % 24 if int(minute) > 0 else int(hour)


def next_fire_times(cron: str, count: int = 3, after: Optional[datetime] = None) -> list:
    """The next ``count`` fire instants, for the settings preview."""
    try:
        trigger = CronTrigger.from_crontab(cron.strip(), timezone=_local_tz())
    except Exception:
        return []
    moment = _aware(after) if after else datetime.now(_local_tz())
    out = []
    for _ in range(max(0, count)):
        moment = trigger.get_next_fire_time(moment, moment)
        if moment is None:
            break
        out.append(moment)
    return out


def outbound_cron_is_hourly(cron: Optional[str]) -> bool:
    """Does the outbound dispatch cron fire at least once an hour?

    Store schedules are only evaluated when outbound dispatch runs, so this is
    the one deployment-side prerequisite. Left at a daily cron, every store
    schedule is silently ignored except in that one hour.
    """
    raw = (cron or "").strip()
    parts = raw.split()
    if len(parts) != 5:
        return False
    # Hourly or finer means the hour field covers every hour. A minute-field
    # pattern is irrelevant — one fire an hour is enough for a one-hour window.
    return parts[1] == "*" or parts[1].startswith("*/")


# ─────────────────────────────────────────────
# Resolution
# ─────────────────────────────────────────────
def pick_cron(store_cron: Optional[str], hospital_cron: Optional[str]) -> tuple:
    """Pure resolution: store override > hospital default > system default.

    Deliberately NOT routed through ``settings.resolve_all``: a store's
    ``settings_priority`` may drop the store or hospital level, which would make
    the generic walk disagree with what the dispatch loop actually does. One
    key, one resolver.
    """
    if (store_cron or "").strip():
        return store_cron.strip(), SOURCE_STORE
    if (hospital_cron or "").strip():
        return hospital_cron.strip(), SOURCE_HOSPITAL
    return DEFAULT_INDENT_CRON, SOURCE_DEFAULT


def resolve_store_cron(db: Session, store_id: int) -> tuple:
    """``(cron, source)`` for one store. Three gets; for a whole run use
    :func:`load_store_crons`, which does it in three queries total."""
    ss = db.get(StoreSettings, store_id)
    store = db.get(Store, store_id)
    hs = db.get(HospitalSettings, store.hospital_id) if store else None
    cron, source = pick_cron(
        getattr(ss, "indent_schedule_cron", None),
        getattr(hs, "indent_schedule_cron", None),
    )
    if source == SOURCE_DEFAULT:
        log.warning(
            "store %s has no indent schedule at store or hospital level — "
            "falling back to %r", store_id, cron,
        )
    return cron, source


def load_store_crons(db: Session) -> dict:
    """``{store_id: (cron, source)}`` for every store, in three queries.

    The dispatch loop resolves 200 stores per run; doing it with
    :func:`resolve_store_cron` would be 600 gets.
    """
    store_crons = dict(
        db.query(StoreSettings.store_id, StoreSettings.indent_schedule_cron).all()
    )
    hospital_crons = dict(
        db.query(HospitalSettings.hospital_id, HospitalSettings.indent_schedule_cron).all()
    )
    out = {}
    for store_id, hospital_id in db.query(Store.id, Store.hospital_id).all():
        cron, source = pick_cron(store_crons.get(store_id), hospital_crons.get(hospital_id))
        if source == SOURCE_DEFAULT:
            log.warning(
                "store %s (hospital %s) has no indent schedule — falling back to %r",
                store_id, hospital_id, cron,
            )
        out[store_id] = (cron, source)
    return out


# ─────────────────────────────────────────────
# Due detection
# ─────────────────────────────────────────────
def due_fire(cron: str, now: datetime, *, window_hours: int = TICK_HOURS) -> Optional[datetime]:
    """The cron fire instant inside ``(now - window_hours, now]``, else None.

    Returns the fire itself, not a boolean, because the caller stores it as the
    double-run guard (``StoreSettings.last_indent_fire_at``): recording the
    *fire* rather than the *run time* makes the guard exact regardless of tick
    jitter or a restart mid-run.

    An unparseable expression returns None — the store is skipped, loudly, not
    generated on every tick.
    """
    try:
        trigger = CronTrigger.from_crontab((cron or "").strip(), timezone=_local_tz())
    except Exception:
        log.warning("unparseable indent schedule %r — store skipped", cron)
        return None
    now = _aware(now)
    window_start = now - timedelta(hours=max(1, int(window_hours)))
    # get_next_fire_time returns the first fire STRICTLY after window_start,
    # which is what makes the window half-open: a fire exactly on the previous
    # boundary belongs to the previous tick and is not re-run here.
    fire = trigger.get_next_fire_time(window_start, window_start)
    if fire is not None and fire <= now:
        return fire
    return None


def is_same_fire(stored: Optional[datetime], fire: Optional[datetime]) -> bool:
    """Is ``stored`` (from ``last_indent_fire_at``) the same fire as ``fire``?

    Tolerates a naive ``stored`` — SQLite drops the offset that Postgres keeps,
    and comparing naive to aware raises — and sub-second drift from storage
    round-tripping.
    """
    if stored is None or fire is None:
        return False
    return abs((_aware(stored) - _aware(fire)).total_seconds()) < 1


def record_store_run(
    db: Session,
    store_id: int,
    fire: Optional[datetime],
    status: str,
    error: Optional[str] = None,
) -> None:
    """Persist the outcome of one store's scheduled run, and commit.

    Committed per store rather than at the end of the run so that a crash
    halfway through cannot replay the stores that already completed — the
    double-run guard is only worth having if it is durable.
    """
    ss = db.get(StoreSettings, store_id)
    if ss is None:
        ss = StoreSettings(store_id=store_id)
        db.add(ss)
    if fire is not None:
        ss.last_indent_fire_at = fire
    ss.last_indent_run_status = status[:20]
    ss.last_indent_error = error[:1000] if error else None
    db.commit()
