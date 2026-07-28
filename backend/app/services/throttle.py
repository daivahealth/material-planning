"""
Login brute-force protection.

Failed attempts are counted per **username** and per **source IP** over a
sliding window; once a key exceeds the limit it is locked for a cooling-off
period and further attempts are refused with 429 before any password check.

Counting both keys matters: per-username alone lets one attacker spray many
accounts from a single host, and per-IP alone lets a botnet grind one account.

State is in-process (no extra infrastructure). That is sufficient for the
single-backend deployment this app ships with; with multiple replicas each
process enforces its own share, so use a shared store (or an edge rate limiter)
if you scale out.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional, Tuple

from app.config import settings

_lock = threading.Lock()
# key -> (list of failure timestamps, locked_until)
_state: Dict[str, Tuple[List[float], float]] = {}


def _limits() -> Tuple[int, float, float]:
    return (
        settings.login_max_attempts,
        settings.login_window_minutes * 60.0,
        settings.login_lockout_minutes * 60.0,
    )


def _keys(username: Optional[str], ip: Optional[str]) -> List[str]:
    keys = []
    if username:
        keys.append(f"user:{username.strip().lower()}")
    if ip:
        keys.append(f"ip:{ip}")
    return keys


def retry_after(username: Optional[str], ip: Optional[str]) -> int:
    """Seconds remaining before the caller may try again; 0 when not locked."""
    max_attempts, _window, _lockout = _limits()
    if max_attempts <= 0:
        return 0
    now = time.monotonic()
    longest = 0.0
    with _lock:
        for key in _keys(username, ip):
            _times, locked_until = _state.get(key, ([], 0.0))
            longest = max(longest, locked_until - now)
    return int(longest) + 1 if longest > 0 else 0


def record_failure(username: Optional[str], ip: Optional[str]) -> bool:
    """Count a failed attempt. Returns True if this tripped a new lockout."""
    max_attempts, window, lockout = _limits()
    if max_attempts <= 0:
        return False
    now = time.monotonic()
    tripped = False
    with _lock:
        for key in _keys(username, ip):
            times, locked_until = _state.get(key, ([], 0.0))
            times = [t for t in times if now - t < window]   # drop stale
            times.append(now)
            if len(times) >= max_attempts and locked_until <= now:
                locked_until = now + lockout
                tripped = True
                times = []        # restart counting after the lock expires
            _state[key] = (times, locked_until)
    return tripped


def clear(username: Optional[str], ip: Optional[str]) -> None:
    """Reset counters after a successful login."""
    with _lock:
        for key in _keys(username, ip):
            _state.pop(key, None)


def reset_all() -> None:
    """Test helper — drop all throttle state."""
    with _lock:
        _state.clear()
