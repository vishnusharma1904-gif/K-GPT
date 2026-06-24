"""K-GPT entitlements service (Epic B) — DB-backed quota engine.

Wraps the pure `quota_policy` with persistence: lazy resets, cap checks,
metering, the weekly-bonus claim, auto-tiering, and admin grants/resets.

Flow per chat request:
    user = refresh(user)          # lazy daily/weekly reset + cap reconcile
    check_access(user)            # raise structured 402/429 if blocked
    ... call the model ...
    record_usage(user_id, ...)    # atomic increment + usage_log

All student-facing surfaces read `usage_view(user)` which returns ONLY a
percentage and a coarse state — never a token count.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.db import supabase_client as db
from app.services import quota_policy as p


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# --- Lazy resets + cap reconcile --------------------------------------------
def refresh(user: dict) -> dict:
    """Apply any due daily/weekly resets and keep daily_cap in sync with tier.

    Correct even if the nightly job never ran: every request self-heals.
    """
    now = _now()
    patch: dict = {}

    # Daily reset → snapshot the completed day into usage_daily, then zero.
    if p.daily_reset_due(now, _dt(user.get("daily_reset_at"))):
        prev_reset = _dt(user.get("daily_reset_at"))
        if prev_reset is not None:
            completed_day = (prev_reset.astimezone(p.IST) - timedelta(days=1)).date()
            used = user.get("daily_used") or 0
            cap = user.get("daily_cap") or p.NORMAL_DAILY_CAP
            try:
                db.rpc_bump_usage_daily(user["id"], completed_day.isoformat(),
                                        int(used), 0, used >= cap)
            except Exception:
                pass  # snapshot is best-effort; never block a chat on it
        patch["daily_used"] = 0
        patch["weekly_bonus_claimed_today"] = 0   # the claimed boost is for one day
        patch["daily_reset_at"] = p.next_daily_reset(now).isoformat()

    # Weekly bonus re-arm.
    if p.weekly_bonus_due(now, _dt(user.get("weekly_bonus_reset_at"))):
        patch["weekly_bonus_available"] = True
        patch["weekly_bonus_reset_at"] = p.next_weekly_reset(now).isoformat()

    # Keep the cap consistent with the tier (handles tier changes / drift).
    expected_cap = p.cap_for_tier(user.get("tier", "normal"))
    if (user.get("daily_cap") or 0) != expected_cap:
        patch["daily_cap"] = expected_cap

    if patch:
        user = db.update_user(user["id"], patch)
    return user


# --- Effective budget + the percentage-only view ----------------------------
def _effective_cap(user: dict) -> int:
    return p.effective_cap(
        user.get("daily_cap") or 0,
        user.get("weekly_bonus_claimed_today") or 0,
        user.get("bonus_balance") or 0,
    )


def usage_view(user: dict) -> dict:
    """Student-facing usage. PERCENTAGE ONLY — no token integers leave here."""
    eff = _effective_cap(user)
    pct = p.percent_used(user.get("daily_used") or 0, eff)
    return {
        "percent_used": pct,
        "state": p.usage_state(pct),
        "tier": user.get("tier", "normal"),
        "weekly_bonus_available": bool(user.get("weekly_bonus_available")),
        "resets_in_seconds": p.resets_in_seconds(_now(), _dt(user.get("daily_reset_at"))),
        "warnings": p.warnings_for(pct),
        "sub_status": user.get("sub_status"),
    }


# --- Access gate ------------------------------------------------------------
def check_access(user: dict) -> None:
    """Raise a structured error if the user can't chat. Admins bypass."""
    if user.get("role") == "admin":
        return
    if user.get("suspended"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Your account is paused. Please contact the admin.")
    if user.get("sub_status") != "active":
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            "No active subscription. Pay the semester fee to use K-GPT.")

    # Daily cap (persistent DB counter).
    eff = _effective_cap(user)
    if p.is_over_cap(user.get("daily_used") or 0, eff):
        secs = p.resets_in_seconds(_now(), _dt(user.get("daily_reset_at")))
        hrs, mins = secs // 3600, (secs % 3600) // 60
        bonus = " You can use your weekly bonus for more today." \
            if user.get("weekly_bonus_available") else ""
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You've reached today's limit. It resets in {hrs}h {mins}m.{bonus}",
        )

    # Weekly hard cap (shared across replicas via Redis; no-op if Redis is off).
    from app.db import redis_client
    weekly_used = redis_client.rate_current(user["id"], "tokens_weekly")
    if weekly_used >= p.WEEKLY_CAP:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You have reached the hard weekly limit of {p.WEEKLY_CAP:,} tokens. Please wait for the weekly reset.",
        )


def should_downshift(user: dict) -> bool:
    """Near the cap → force cheapest models to stretch the remaining budget."""
    if user.get("role") == "admin":
        return False
    pct = p.percent_used(user.get("daily_used") or 0, _effective_cap(user))
    return p.should_downshift(pct)


# --- Metering ---------------------------------------------------------------
def record_usage(user_id: str, model: str, p_tok: int, c_tok: int, cost: float) -> None:
    db.log_usage(user_id, model, p_tok, c_tok, cost)
    # Frontier models drain the daily cap faster (e.g. 3.5x) regardless of the raw
    # token count. usage_log keeps the real tokens; the daily bucket is weighted.
    from app.services import smart_router
    from app.db import redis_client

    billed = int(round((p_tok + c_tok) * smart_router.cost_multiplier(model)))

    # 1. Persistent DB counter — the source of truth for daily tracking + tiering.
    db.rpc_increment_daily_usage(user_id, billed)

    # 2. Fast Redis buckets — shared across replicas for the daily/weekly hard
    #    caps. Both add `billed` (not 1) and refresh their TTL. No-op without Redis.
    _DAY, _WEEK = 86_400, 604_800
    redis_client.incr_by(user_id, "tokens_daily", billed, _DAY)
    redis_client.incr_by(user_id, "tokens_weekly", billed, _WEEK)


# --- Weekly bonus claim -----------------------------------------------------
def claim_weekly_bonus(user: dict) -> dict:
    user = refresh(user)
    if not user.get("weekly_bonus_available"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Weekly bonus already used. It refreshes weekly.")
    ok = db.rpc_claim_weekly_bonus(
        user["id"], p.WEEKLY_BONUS, p.next_weekly_reset(_now()).isoformat())
    if not ok:
        raise HTTPException(status.HTTP_409_CONFLICT, "Weekly bonus already used.")
    db.insert_entitlement_log(None, user["id"], "claim_weekly_bonus", p.WEEKLY_BONUS,
                              "student self-claim")
    return usage_view(db.get_user(user["id"]))


# --- Auto-tiering (nightly) -------------------------------------------------
def apply_tiering(user: dict) -> str | None:
    """Decide + persist a tier change from completed-day history. Returns new tier or None."""
    hist = db.get_usage_daily(user["id"], days=14)
    tokens = [int(r["tokens"]) for r in hist]
    last7, last14 = tokens[:7], tokens[:14]
    decided = p.tiering_decision(
        user.get("tier", "normal"), bool(user.get("tier_override")), last7, last14)
    if decided != user.get("tier"):
        db.update_user(user["id"], {"tier": decided, "daily_cap": p.cap_for_tier(decided)})
        db.insert_entitlement_log(None, user["id"], "auto_tier", 0,
                                  f"{user.get('tier')} -> {decided}")
        return decided
    return None


def run_nightly() -> dict:
    """Refresh + auto-tier every paid student. Idempotent; safe to run repeatedly."""
    users = db.list_paid_users()
    changed = 0
    for u in users:
        try:
            u = refresh(u)
            if apply_tiering(u):
                changed += 1
        except Exception:
            continue
    expired = expire_due_subscriptions()
    return {"processed": len(users), "tier_changes": changed, "expired": expired}


def expire_due_subscriptions(grace_days: int = 3) -> int:
    """Mark subscriptions past their expiry (+grace) as expired. Returns count."""
    cutoff = (_now() - timedelta(days=grace_days)).isoformat()
    try:
        due = db.list_expired_active_users(cutoff)
    except Exception:
        return 0
    n = 0
    for u in due:
        try:
            db.update_user(u["id"], {"sub_status": "expired"})
            db.insert_entitlement_log(None, u["id"], "sub_expired", 0, "auto expiry")
            n += 1
        except Exception:
            continue
    return n


# --- Admin actions (all audit-logged) ---------------------------------------
def admin_reset_daily(actor_id: str, target_id: str) -> None:
    db.update_user(target_id, {"daily_used": 0})
    db.insert_entitlement_log(actor_id, target_id, "reset_daily", 0, "admin reset")


def admin_grant_tokens(actor_id: str, target_id: str, tokens: int) -> None:
    u = db.get_user(target_id)
    db.update_user(target_id, {"bonus_balance": (u.get("bonus_balance") or 0) + tokens})
    db.insert_entitlement_log(actor_id, target_id, "grant_tokens", tokens, "admin grant")


def admin_set_tier(actor_id: str, target_id: str, tier: str) -> None:
    tier = "heavy" if tier == "heavy" else "normal"
    db.update_user(target_id, {"tier": tier, "tier_override": True,
                               "daily_cap": p.cap_for_tier(tier)})
    db.insert_entitlement_log(actor_id, target_id, "set_tier", 0, f"override -> {tier}")


def admin_clear_override(actor_id: str, target_id: str) -> None:
    db.update_user(target_id, {"tier_override": False})
    db.insert_entitlement_log(actor_id, target_id, "clear_override", 0, "auto-tiering re-enabled")


def admin_refresh_bonus(actor_id: str, target_id: str) -> None:
    db.update_user(target_id, {"weekly_bonus_available": True})
    db.insert_entitlement_log(actor_id, target_id, "refresh_bonus", 0, "admin re-armed bonus")


def admin_set_suspended(actor_id: str, target_id: str, suspended: bool) -> None:
    db.update_user(target_id, {"suspended": suspended})
    db.insert_entitlement_log(actor_id, target_id,
                              "suspend" if suspended else "restore", 0, "admin")
