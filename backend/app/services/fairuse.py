"""Fair-use guardrails (Phase 14) — abuse / DoS protection.

Protects the token budget and the API from runaway use, credential sharing, and
unauthenticated floods:
  * per-user sliding-window rate limit (requests/minute)
  * per-user concurrency cap (no fan-out from a shared login)
  * per-IP / per-target limits for unauthenticated auth endpoints (stops
    signup spam, login brute force, and OTP/reset email-bombing)
  * shared-login anomaly: too many distinct IPs for one account in a day

Backed by **Redis** when configured so the limits are correct across multiple
uvicorn workers / replicas (a single in-memory dict per process would let an
attacker get N× the limit). Falls back to process-local counters when Redis is
absent. Admins are exempt from the per-user chat limits.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

from app.db import redis_client

RATE_PER_MIN = 20
MAX_CONCURRENT = 3
DISTINCT_IP_ALERT = 4         # >4 IPs/day for one account looks shared

# In-memory fallbacks (used only when Redis is not configured).
_hits: dict[str, deque] = defaultdict(lambda: deque(maxlen=RATE_PER_MIN + 5))
_active: dict[str, int] = defaultdict(int)
_ip_hits: dict[str, deque] = defaultdict(lambda: deque(maxlen=64))
_ips: dict[str, set] = defaultdict(set)
_ips_day: dict[str, str] = {}


def check_rate(user_id: str, is_admin: bool) -> None:
    """Per-user requests/minute cap (chat). Admins/faculty (privileged) bypass."""
    if is_admin:
        return
    if redis_client.configured():
        if not redis_client.rate_check(user_id, "rpm", RATE_PER_MIN, 60):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "You're sending messages too fast. Give it a few seconds.")
        return
    # in-memory fallback
    now = time.time()
    dq = _hits[user_id]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= RATE_PER_MIN:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "You're sending messages too fast. Give it a few seconds.")
    dq.append(now)


def check_ip_rate(key: str | None, action: str, limit: int, window_seconds: int = 60) -> None:
    """Throttle an UNAUTHENTICATED action by an arbitrary key — a client IP OR an
    email address, depending on the caller (e.g. auth.py uses IPs for signup/login
    and emails for verify-otp/resend/forgot so one account can't be hammered from
    many IPs). Raises 429 over the limit. Best-effort: no key (e.g. missing IP
    header) → allowed."""
    if not key:
        return
    if redis_client.configured():
        # rate_check namespaces the key as rate:{key}:{action}.
        if not redis_client.rate_check(f"ip:{key}", action, limit, window_seconds):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many attempts. Please wait a bit and try again.")
        return
    # in-memory fallback
    now = time.time()
    dq = _ip_hits[f"{key}:{action}"]
    while dq and now - dq[0] > window_seconds:
        dq.popleft()
    if len(dq) >= limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many attempts. Please wait a bit and try again.")
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
    """Context manager enforcing a per-user concurrent-request cap (Redis-shared
    when configured). Admins bypass."""
    def __init__(self, user_id: str, is_admin: bool):
        self.user_id, self.is_admin = user_id, is_admin
        self._redis = redis_client.configured()

    def __enter__(self):
        if self.is_admin:
            return self
        if self._redis:
            if not redis_client.concurrency_acquire(self.user_id, MAX_CONCURRENT, ttl=120):
                # Acquire failed — no slot was taken, so do NOT release one here.
                # Releasing on a failed acquire would decrement another in-flight
                # request's real slot, letting concurrency exceed MAX_CONCURRENT.
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    "Too many messages in flight. Wait for the current reply.")
            return self
        if _active[self.user_id] >= MAX_CONCURRENT:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many messages in flight. Wait for the current reply.")
        _active[self.user_id] += 1
        return self

    def __exit__(self, *exc):
        if self.is_admin:
            return False
        if self._redis:
            redis_client.concurrency_release(self.user_id)
        else:
            _active[self.user_id] = max(0, _active[self.user_id] - 1)
        return False
