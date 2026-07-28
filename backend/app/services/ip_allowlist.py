"""
In-memory cache for the IP allowlist.

The filter runs on *every* request, so it must never hit the database on the hot
path. The enabled rules are loaded once into a module-level cache and reused
until something invalidates it:

  * a write through the API calls ``invalidate()`` → next request reloads;
  * a TTL reload (``_TTL_SECONDS``) picks up changes made by another worker or
    replica, or directly in the database, without a restart.

Fails **open**: if the table is missing or unreadable the cache resolves to
"no rules", which allows all traffic. A security filter that cannot read its
configuration must not lock every user out of a hospital system.
"""
from __future__ import annotations

import ipaddress
import logging
import threading
import time
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.security import AllowedIP

log = logging.getLogger("security")

_TTL_SECONDS = 30.0

_lock = threading.Lock()
_networks: List[ipaddress._BaseNetwork] = []
_loaded_at: float = 0.0
_valid: bool = False


def parse_cidr(value: str) -> ipaddress._BaseNetwork:
    """Parse a single address or CIDR range. Raises ValueError if malformed.

    ``strict=False`` lets ``10.1.2.3/24`` be entered without complaint about
    host bits; it is normalised to the containing network.
    """
    text = (value or "").strip()
    if not text:
        raise ValueError("IP address or CIDR range is required")
    return ipaddress.ip_network(text, strict=False)


def invalidate() -> None:
    """Drop the cache so the next check reloads from the database."""
    global _valid
    with _lock:
        _valid = False


def networks_from_db(db: Session) -> List[ipaddress._BaseNetwork]:
    """Enabled networks read straight from the session, **bypassing the cache**.

    Used by the admin lock-out guard, which must evaluate rules that are only
    flushed (not committed). Populating the shared cache from an uncommitted
    transaction would let a rolled-back rule start enforcing for every request.
    """
    nets: List[ipaddress._BaseNetwork] = []
    for (cidr,) in db.query(AllowedIP.cidr).filter(AllowedIP.enabled.is_(True)).all():
        try:
            nets.append(parse_cidr(cidr))
        except ValueError:
            log.warning("ignoring malformed allowlist entry %r", cidr)
    return nets


def _load(db: Session) -> None:
    global _networks, _loaded_at, _valid
    nets: List[ipaddress._BaseNetwork] = []
    try:
        rows = db.query(AllowedIP.cidr).filter(AllowedIP.enabled.is_(True)).all()
        for (cidr,) in rows:
            try:
                nets.append(parse_cidr(cidr))
            except ValueError:
                # A malformed row must not take the whole allowlist down.
                log.warning("ignoring malformed allowlist entry %r", cidr)
    except Exception as exc:
        # Table missing / DB down → fail open rather than lock everyone out.
        log.warning("could not load IP allowlist (%s) — allowing all traffic", exc)
        nets = []
    with _lock:
        _networks = nets
        _loaded_at = time.monotonic()
        _valid = True


def get_networks(db: Session) -> List[ipaddress._BaseNetwork]:
    """Cached list of enabled networks, reloading on invalidation or TTL."""
    with _lock:
        fresh = _valid and (time.monotonic() - _loaded_at) < _TTL_SECONDS
        if fresh:
            return _networks
    _load(db)
    with _lock:
        return _networks


def is_allowed(db: Session, ip: Optional[str]) -> Tuple[bool, bool]:
    """``(allowed, enforcing)`` for a client IP.

    ``enforcing`` is False when no rules are configured — in that mode every
    request is allowed and the filter is effectively off.
    """
    nets = get_networks(db)
    if not nets:
        return True, False           # nothing configured → allow all
    if not ip:
        return False, True           # enforcing but no usable source address
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False, True
    return any(addr in n for n in nets), True


def covers(nets: List[ipaddress._BaseNetwork], ip: Optional[str]) -> bool:
    """True if `ip` falls inside any of `nets` — used for the lock-out guard."""
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in n for n in nets)
