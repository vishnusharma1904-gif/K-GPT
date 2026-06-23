"""Fair-use guardrails (Phase 14) — lightweight, in-process.

Protects the token budget from runaway use and credential sharing:
  * per-user sliding-window rate limit (requests/minute)
  * per-user concurrency cap (no fan-out from a shared login)
  * shared-login anomaly: too many distinct IPs for one account in a day

In-memory is fine for a single backend; swap for Redis when you scale to
multiple instances (noted in DEPLOYMENT). Admins are exempt.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

RATE_PER_MIN = 20
MAX_CONCURRENT = 3
DISTINCT_IP_ALERT = 4         # >4 IPs/day for one account looks shared

_hits: dict[str, deque] = defaultdict(lambda: deque(maxlen=RATE_PER_MIN + 5))
_active: dict[str, int] = defaultdict(int)
_ips: dict[str, set] = defaultdict(set)
_ips_day: dict[str, str] = {}


def check_rate(user_id: str, is_admin: bool) -> None:
    if is_admin:
        return
    now = time.time()
    dq = _hits[user_id]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= RATE_PER_MIN:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "You're sending messages too fast. Give it a few seconds.")
    dq.append(now)


def note_ip(user_id: str, ip: str | None) -> bool:
    """Track distinct IPs per UTC day. Returns True if it looks like a shared login."""
    if not ip:
        return False
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if _ips_day.get(user_id) != today:
        _ips_day[user_id] = today
        _ips[user_id] = set()
    _ips[user_id].add(ip)
    return len(_ips[user_id]) > DISTINCT_IP_ALERT


class concurrency:
    """Context manager enforcing a per-user concurrent-request cap."""
    def __init__(self, user_id: str, is_admin: bool):
        self.user_id, self.is_admin = user_id, is_admin

    def __enter__(self):
        if not self.is_admin and _active[self.user_id] >= MAX_CONCURRENT:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many messages in flight. Wait for the current reply.")
        _active[self.user_id] += 1
        return self

    def __exit__(self, *exc):
        _active[self.user_id] = max(0, _active[self.user_id] - 1)
        return False
