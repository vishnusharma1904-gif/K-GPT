"""K-GPT quota policy — PURE functions, no I/O.

Design reasoning (the "chain of thought" behind each rule):

1. Two paid daily tiers exist only to size the daily bucket:
      Normal  = 500,000 tokens/day
      Heavy   = 1,000,000 tokens/day
   "Heavy" is a *usage classification*, not a different product — so the tier is
   derived from behaviour (or pinned by an admin), never bought directly here.

2. A student's spendable budget *today* is not just the tier cap. It is:
      effective_cap = daily_cap
                    + claimed_weekly_bonus_today (100k, if claimed)
                    + bonus_balance (admin one-off grants, persistent)
   Keeping these three sources explicit makes resets unambiguous: the daily
   reset zeroes only `daily_used`; admin grants survive; the weekly bonus is a
   once-per-7-days top-up.

3. We NEVER expose token integers to students. The only number they see is a
   percentage of their effective cap, plus a coarse state label. So the policy
   exposes `percent_used` + `usage_state`, and the API layer returns nothing else.

4. Auto-tiering must reward sustained heavy use, not a single spike, and must be
   reversible — but an explicit admin decision must always win (sticky override).

These are pure functions so they can be unit-tested deterministically without a
database or a clock.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# --- Constants ---------------------------------------------------------------
NORMAL_DAILY_CAP = 500_000
HEAVY_DAILY_CAP = 1_000_000
WEEKLY_BONUS = 100_000
MONTHLY_DAILY_CAP = 150_000   # ₹100 monthly plan tier

# Auto-tiering thresholds
PROMOTE_RATIO = 0.80          # "high-usage day" = >= 80% of the Normal cap
PROMOTE_DAYS_REQUIRED = 4     # ... on >= 4 of the last 7 days
PROMOTE_WINDOW = 7
DEMOTE_RATIO = 0.40           # sustained usage below 40% of Normal cap ...
DEMOTE_WINDOW = 14            # ... across 14 days -> demote

# Near-cap behaviour
DOWNSHIFT_PERCENT = 95        # at/above this %, force the cheapest models
WARN_PERCENTS = (75, 95)      # soft-limit nudges

IST = ZoneInfo("Asia/Kolkata")


# --- Tier / cap --------------------------------------------------------------
def cap_for_tier(tier: str) -> int:
    if tier == "heavy":
        return HEAVY_DAILY_CAP
    if tier == "monthly":
        return MONTHLY_DAILY_CAP
    return NORMAL_DAILY_CAP


def effective_cap(daily_cap: int, claimed_bonus_today: int, bonus_balance: int) -> int:
    """Total spendable tokens for *today*, across all three budget sources."""
    return max(0, daily_cap) + max(0, claimed_bonus_today) + max(0, bonus_balance)


# --- The percentage-only display contract ------------------------------------
def percent_used(daily_used: int, eff_cap: int) -> int:
    """Integer 0..100. The ONLY usage number a student ever sees."""
    if eff_cap <= 0:
        return 100
    return max(0, min(100, math.floor(daily_used / eff_cap * 100)))


def usage_state(pct: int) -> str:
    if pct >= 100:
        return "reached"
    if pct >= 95:
        return "almost"
    if pct >= 75:
        return "getting_close"
    return "comfortable"


def is_over_cap(daily_used: int, eff_cap: int) -> bool:
    return daily_used >= eff_cap


def should_downshift(pct: int) -> bool:
    """Near the cap, route to the cheapest models to stretch the remaining budget."""
    return pct >= DOWNSHIFT_PERCENT


def warnings_for(pct: int) -> list[int]:
    return [w for w in WARN_PERCENTS if pct >= w]


# --- Time / resets -----------------------------------------------------------
def next_daily_reset(now: datetime) -> datetime:
    """Next 00:00 IST, returned as a UTC-aware datetime."""
    now_ist = now.astimezone(IST)
    tomorrow = (now_ist + timedelta(days=1)).date()
    reset_ist = datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=IST)
    return reset_ist.astimezone(timezone.utc)


def daily_reset_due(now: datetime, daily_reset_at: datetime | None) -> bool:
    return daily_reset_at is None or now >= daily_reset_at


def resets_in_seconds(now: datetime, daily_reset_at: datetime | None) -> int:
    if daily_reset_at is None:
        return 0
    return max(0, int((daily_reset_at - now).total_seconds()))


def next_weekly_reset(now: datetime) -> datetime:
    """Weekly bonus re-arms 7 days from now."""
    return now.astimezone(timezone.utc) + timedelta(days=7)


def weekly_bonus_due(now: datetime, weekly_bonus_reset_at: datetime | None) -> bool:
    return weekly_bonus_reset_at is None or now >= weekly_bonus_reset_at


# --- Auto-tiering decision ---------------------------------------------------
def tiering_decision(current_tier: str, override: bool,
                     last7_tokens: list[int], last14_tokens: list[int]) -> str:
    """Return the tier a user SHOULD have given their completed-day history.

    - Admin override is sticky: never auto-change an overridden user.
    - Promotion (to heavy) is checked first and wins over demotion.
    - Promote: >= 80% of the Normal cap on >= 4 of the last 7 days.
    - Demote: every one of the last 14 days stayed below 40% of the Normal cap.
    - Otherwise: no change.
    """
    if override:
        return current_tier

    high_days = sum(1 for t in last7_tokens if t >= PROMOTE_RATIO * NORMAL_DAILY_CAP)
    if high_days >= PROMOTE_DAYS_REQUIRED:
        return "heavy"

    if last14_tokens and max(last14_tokens) < DEMOTE_RATIO * NORMAL_DAILY_CAP:
        return "normal"

    return current_tier
