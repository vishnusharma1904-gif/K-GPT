"""Admin console API (owner-only) — students, entitlements, tiering, audit.

Every mutating action is recorded in `entitlement_log`. Token integers are
visible to the admin here (analytics), never to students.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import require_admin
from app.core.config import get_settings
from app.db import supabase_client as db
from app.db import qdrant_client
from app.services import entitlements, safety
from app.services import quota_policy as qp

settings = get_settings()
router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# --- Shared knowledge base (admin-managed institution documents) ------------
@router.get("/knowledge")
async def list_knowledge(_: dict = Depends(require_admin)):
    """List documents in the institution-wide shared knowledge base with real-time status."""
    if settings.qdrant_host:
        actual_docs = qdrant_client.list_shared_documents()
    else:
        actual_docs = db.list_shared_documents()

    actual_map = {d["source"]: d for d in actual_docs}
    registry_docs = db.list_shared_registry_documents()

    merged_docs = []
    seen_sources = set()

    for r in registry_docs:
        source = r.get("filename")
        if not source:
            # Defensive: skip a partially-written registry row instead of
            # crashing the whole admin knowledge list.
            continue
        seen_sources.add(source)

        actual = actual_map.get(source)
        chunks = r.get("chunk_count") or 0
        if actual and actual.get("chunks"):
            chunks = max(chunks, actual["chunks"])

        metadata = r.get("metadata") or {}
        scope = metadata.get("scope") or {}

        merged_docs.append({
            "source": source,
            "chunks": chunks,
            "created_at": r.get("created_at"),
            "status": r.get("status") or "ready",
            "error": metadata.get("error"),
            "scope_branch": scope.get("branch"),
            "scope_year": scope.get("year"),
            "scope_section": scope.get("section"),
        })

    for source, actual in actual_map.items():
        if source not in seen_sources:
            merged_docs.append({
                "source": source,
                "chunks": actual.get("chunks") or 0,
                "created_at": actual.get("created_at"),
                "status": "ready",
                "error": None,
                "scope_branch": actual.get("scope_branch"),
                "scope_year": actual.get("scope_year"),
                "scope_section": actual.get("scope_section"),
            })

    def get_sort_key(d):
        ts = d.get("created_at")
        if not ts:
            return ""
        return str(ts)

    merged_docs.sort(key=get_sort_key, reverse=True)
    return {"documents": merged_docs}


@router.delete("/knowledge")
async def delete_knowledge(source: str, _: dict = Depends(require_admin)):
    """Remove a document (all its chunks) from the shared knowledge base."""
    if not source:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "source is required")
    
    db.delete_registry_document_by_filename(source)
    
    if settings.qdrant_host:
        qdrant_client.delete_shared_document(source)
        return {"ok": True, "source": source}
    removed = db.delete_shared_document(source)
    return {"ok": True, "source": source, "chunks_removed": removed}


# --- request bodies ---------------------------------------------------------
class Targets(BaseModel):
    user_ids: list[str] = Field(min_length=1)


class GrantBody(Targets):
    tokens: int = Field(gt=0, le=10_000_000)


class TierBody(Targets):
    tier: str  # 'normal' | 'heavy'


class SuspendBody(Targets):
    suspended: bool


def _admin_view(u: dict) -> dict:
    """Admin sees real numbers + the student's %; never exposed to students."""
    cap = qp.effective_cap(u.get("daily_cap") or 0,
                           u.get("weekly_bonus_claimed_today") or 0,
                           u.get("bonus_balance") or 0)
    return {
        "id": u["id"], "full_name": u.get("full_name"), "email": u.get("email"),
        "roll_no": u.get("roll_no"), "role": u.get("role"),
        "sub_status": u.get("sub_status"), "suspended": u.get("suspended"),
        "tier": u.get("tier"), "tier_override": u.get("tier_override"),
        "weekly_bonus_available": u.get("weekly_bonus_available"),
        "daily_used": u.get("daily_used"), "daily_cap": u.get("daily_cap"),
        "bonus_balance": u.get("bonus_balance"),
        "plan": u.get("plan"), "monitored": safety.is_monitored(u),
        "percent_used": qp.percent_used(u.get("daily_used") or 0, cap),
        "course": u.get("course"), "branch": u.get("branch"),
        "section": u.get("section"), "admission_year": u.get("admission_year"),
        "department": u.get("department"), "mobile": u.get("mobile"),
        "faculty_approved": bool(u.get("faculty_approved")),
        "year": _cohort_year(u)[0], "semester": _cohort_year(u)[1],
    }


def _cohort_year(u: dict):
    from app.services import cohort
    return cohort.derive(u.get("admission_year"), u.get("course"))


# --- overview ---------------------------------------------------------------
@router.get("/stats")
async def stats(_: dict = Depends(require_admin)):
    users = db.list_users(limit=5000)
    active = [u for u in users if u.get("sub_status") == "active"]
    faculty = [u for u in users if u.get("role") == "faculty"]
    return {
        "total_users": len(users),
        "active_subs": len(active),
        "students": len([u for u in users if u.get("role") == "student"]),
        "faculty": len(faculty),
        "pending_faculty": len([u for u in faculty if not u.get("faculty_approved")]),
        "heavy_tier": len([u for u in users if u.get("tier") == "heavy"]),
        "suspended": len([u for u in users if u.get("suspended")]),
        "total_tokens_used": sum((u.get("used_tokens") or 0) for u in users),
    }


@router.get("/users")
async def users(_: dict = Depends(require_admin)):
    return [_admin_view(u) for u in db.list_users(limit=5000)]


@router.get("/users/{user_id}/log")
async def entitlement_log(user_id: str, _: dict = Depends(require_admin)):
    return db.get_entitlement_log(user_id)


# --- subscription (kept from M1) -------------------------------------------
@router.post("/users/{user_id}/grant-access")
async def grant_access(user_id: str, months: int = 6, admin: dict = Depends(require_admin)):
    from datetime import datetime, timedelta, timezone
    expires = (datetime.now(timezone.utc) + timedelta(days=30 * months)).isoformat()
    db.update_user(user_id, {"sub_status": "active", "sub_expires_at": expires})
    db.insert_entitlement_log(admin["user_id"], user_id, "grant_access", 0, f"{months} months")
    return {"ok": True, "expires_at": expires}


# --- entitlement actions (single or bulk) ----------------------------------
@router.post("/entitlements/reset-daily")
async def reset_daily(body: Targets, admin: dict = Depends(require_admin)):
    for uid in body.user_ids:
        entitlements.admin_reset_daily(admin["user_id"], uid)
    return {"ok": True, "count": len(body.user_ids)}


@router.post("/entitlements/grant-tokens")
async def grant_tokens(body: GrantBody, admin: dict = Depends(require_admin)):
    for uid in body.user_ids:
        entitlements.admin_grant_tokens(admin["user_id"], uid, body.tokens)
    return {"ok": True, "count": len(body.user_ids), "tokens": body.tokens}


@router.post("/entitlements/set-tier")
async def set_tier(body: TierBody, admin: dict = Depends(require_admin)):
    for uid in body.user_ids:
        entitlements.admin_set_tier(admin["user_id"], uid, body.tier)
    return {"ok": True, "count": len(body.user_ids), "tier": body.tier}


@router.post("/entitlements/clear-override")
async def clear_override(body: Targets, admin: dict = Depends(require_admin)):
    for uid in body.user_ids:
        entitlements.admin_clear_override(admin["user_id"], uid)
    return {"ok": True, "count": len(body.user_ids)}


@router.post("/entitlements/refresh-bonus")
async def refresh_bonus(body: Targets, admin: dict = Depends(require_admin)):
    for uid in body.user_ids:
        entitlements.admin_refresh_bonus(admin["user_id"], uid)
    return {"ok": True, "count": len(body.user_ids)}


@router.post("/entitlements/suspend")
async def suspend(body: SuspendBody, admin: dict = Depends(require_admin)):
    for uid in body.user_ids:
        entitlements.admin_set_suspended(admin["user_id"], uid, body.suspended)
    return {"ok": True, "count": len(body.user_ids), "suspended": body.suspended}


# --- maintenance ------------------------------------------------------------
@router.post("/entitlements/run-nightly")
async def run_nightly(_: dict = Depends(require_admin)):
    """Manually trigger the daily reset + auto-tiering sweep."""
    return entitlements.run_nightly()


# ============================================================================
# Admin v2 — search/filter, analytics, coupons, bulk activation (P44/P45/P18)
# ============================================================================
from datetime import datetime, timedelta, timezone  # noqa: E402
from collections import Counter  # noqa: E402

from pydantic import BaseModel as _BM  # noqa: E402


class CouponBody(_BM):
    code: str
    percent_off: int = Field(ge=1, le=100)
    max_redemptions: int | None = None
    expires_at: str | None = None


class BulkActivateBody(_BM):
    roll_nos: list[str] = Field(min_length=1)
    months: int = 6


@router.get("/users/search")
async def users_search(q: str | None = None, tier: str | None = None,
                       sub_status: str | None = None,
                       year: int | None = None, semester: int | None = None,
                       section: str | None = None, course: str | None = None,
                       branch: str | None = None,
                       _: dict = Depends(require_admin)):
    """Cohort/section filtering + free-text search over name/email/roll (P44).
    Filter by year / semester / section / course / branch to target a cohort."""
    rows = db.list_users(limit=5000)
    ql = (q or "").lower().strip()
    sec = (section or "").upper().strip()
    crs = (course or "").lower().strip()
    brn = (branch or "").lower().strip()
    out = []
    for u in rows:
        if ql and ql not in (
            f"{u.get('full_name','')} {u.get('email','')} {u.get('roll_no','')}".lower()):
            continue
        if tier and u.get("tier") != tier:
            continue
        if sub_status and u.get("sub_status") != sub_status:
            continue
        if year is not None and u.get("year") != year:
            continue
        if semester is not None and u.get("semester") != semester:
            continue
        if sec and (u.get("section") or "").upper() != sec:
            continue
        if crs and crs not in (u.get("course") or "").lower():
            continue
        if brn and brn not in (u.get("branch") or "").lower():
            continue
        out.append(_admin_view(u))
    return {"count": len(out), "users": out}


@router.get("/faculty/pending")
async def faculty_pending(_: dict = Depends(require_admin)):
    """Faculty accounts awaiting approval. Until approved they cannot log in /
    get a session (the account is blocked)."""
    rows = [u for u in db.list_users(limit=5000)
            if u.get("role") == "faculty" and not u.get("faculty_approved")]
    rows.sort(key=lambda u: u.get("created_at") or "", reverse=True)
    return {"count": len(rows), "faculty": [_admin_view(u) for u in rows]}


@router.post("/faculty/{user_id}/approve")
async def faculty_approve(user_id: str, admin: dict = Depends(require_admin)):
    """Approve a faculty account → unblocks login + grants faculty privileges
    (shared-KB upload, no student quota)."""
    u = db.get_user(user_id)
    if not u or u.get("role") != "faculty":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Faculty account not found.")
    db.update_user(user_id, {"faculty_approved": True, "suspended": False,
                             "sub_status": "active"})
    db.insert_entitlement_log(admin["user_id"], user_id, "approve_faculty", 0,
                              u.get("department") or "")
    return {"ok": True, "user_id": user_id, "faculty_approved": True}


@router.post("/faculty/{user_id}/reject")
async def faculty_reject(user_id: str, admin: dict = Depends(require_admin)):
    """Reject/revoke a faculty account → keeps it blocked (unapproved) and
    suspends it so the person cannot use K-GPT."""
    u = db.get_user(user_id)
    if not u or u.get("role") != "faculty":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Faculty account not found.")
    db.update_user(user_id, {"faculty_approved": False, "suspended": True})
    db.insert_entitlement_log(admin["user_id"], user_id, "reject_faculty", 0,
                              u.get("department") or "")
    from app.core.security import bump_token_version
    try:
        bump_token_version(user_id)   # revoke any session immediately
    except Exception:
        logger.exception("faculty_reject: failed to revoke sessions for user_id=%s", user_id)
    return {"ok": True, "user_id": user_id, "faculty_approved": False}


class StudentProfileBody(_BM):
    full_name: str | None = None
    roll_no: str | None = None
    course: str | None = None
    branch: str | None = None
    admission_year: int | None = Field(default=None, ge=2000, le=2100)
    year: int | None = Field(default=None, ge=1, le=5)   # CURRENT year (preferred)
    section: str | None = None
    department: str | None = None
    mobile: str | None = None


@router.patch("/users/{user_id}/profile")
async def set_student_profile(user_id: str, body: StudentProfileBody,
                              _: dict = Depends(require_admin)):
    """Admin-only edit of a student's identity/cohort fields. Students cannot
    change these themselves after onboarding — they request changes here."""
    patch: dict = {}
    if body.full_name is not None:
        patch["full_name"] = body.full_name.strip() or None
    if body.roll_no is not None:
        patch["roll_no"] = (body.roll_no.strip().upper() or None)
    if body.course is not None:
        patch["course"] = body.course.strip() or None
    if body.branch is not None:
        patch["branch"] = (body.branch.strip().upper() or None)
    # Prefer an explicit current-year edit (converted to an effective batch year so
    # the cohort still auto-advances); fall back to a raw admission_year if sent.
    if body.year is not None:
        from app.services import cohort
        patch["admission_year"] = cohort.batch_year_for(body.year)
    elif body.admission_year is not None:
        patch["admission_year"] = body.admission_year
    if body.section is not None:
        patch["section"] = (body.section.strip().upper() or None)
    if body.department is not None:
        patch["department"] = body.department.strip() or None
    if body.mobile is not None:
        raw = body.mobile.strip()
        if not raw:
            patch["mobile"] = None
        else:
            digits = "".join(c for c in raw if c.isdigit())
            if len(digits) == 12 and digits.startswith("91"):
                digits = digits[2:]
            elif len(digits) == 11 and digits.startswith("0"):
                digits = digits[1:]
            if len(digits) != 10 or digits[0] not in "6789":
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    "Enter a valid 10-digit mobile number.")
            patch["mobile"] = digits
    if patch:
        db.update_user(user_id, patch)
    return {"ok": True, "user_id": user_id, **patch}


@router.get("/analytics")
async def analytics(days: int = 14, _: dict = Depends(require_admin)):
    """Adoption + cost trends. Raw tokens are admin-only here (never to students)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days))
    users = db.list_users(limit=5000)

    # tier + subscription distribution
    tier_dist = Counter(u.get("tier", "normal") for u in users if u.get("role") == "student")
    sub_dist = Counter(u.get("sub_status", "inactive") for u in users if u.get("role") == "student")

    # daily activity + cost from the metering tables
    try:
        daily = db.usage_daily_all(since.date().isoformat())
    except Exception:
        daily = []
    try:
        log = db.usage_log_recent(since.isoformat())
    except Exception:
        log = []

    by_day: dict[str, dict] = {}
    for r in daily:
        d = str(r["day"])
        slot = by_day.setdefault(d, {"day": d, "active_users": set(), "tokens": 0})
        slot["active_users"].add(r["user_id"])
        slot["tokens"] += int(r["tokens"])
    series = [{"day": d, "active_users": len(v["active_users"]), "tokens": v["tokens"]}
              for d, v in sorted(by_day.items())]

    model_mix = Counter()
    total_cost = 0.0
    wau = set()
    for r in log:
        if r.get("model") != "error":
            model_mix[r["model"]] += 1
        total_cost += float(r.get("cost_usd") or 0)
        wau.add(r["user_id"])

    return {
        "window_days": days,
        "totals": {
            "students": sum(1 for u in users if u.get("role") == "student"),
            "active_subs": sub_dist.get("active", 0),
            "wau": len(wau),
            "cost_usd": round(total_cost, 4),
        },
        "tier_distribution": dict(tier_dist),
        "sub_distribution": dict(sub_dist),
        "model_mix": model_mix.most_common(12),
        "daily": series,
    }


@router.post("/coupons")
async def create_coupon(body: CouponBody, admin: dict = Depends(require_admin)):
    db.sb().table("coupons").upsert({
        "code": body.code.upper(), "percent_off": body.percent_off,
        "max_redemptions": body.max_redemptions, "expires_at": body.expires_at,
        "active": True,
    }).execute()
    db.insert_entitlement_log(admin["user_id"], admin["user_id"], "create_coupon",
                              body.percent_off, body.code.upper())
    return {"ok": True, "code": body.code.upper()}


@router.get("/coupons")
async def list_coupons(_: dict = Depends(require_admin)):
    return db.sb().table("coupons").select("*").order("created_at", desc=True).execute().data


@router.post("/bulk-activate")
async def bulk_activate(body: BulkActivateBody, admin: dict = Depends(require_admin)):
    """Activate a whole class/section by roll-number list (P18)."""
    expires = (datetime.now(timezone.utc) + timedelta(days=30 * body.months)).isoformat()
    rolls = {r.strip().upper() for r in body.roll_nos if r.strip()}
    users = db.list_users(limit=5000)
    activated = 0
    for u in users:
        if (u.get("roll_no") or "").upper() in rolls:
            db.update_user(u["id"], {"sub_status": "active", "sub_expires_at": expires})
            db.insert_entitlement_log(admin["user_id"], u["id"], "bulk_activate",
                                      0, f"{body.months} months")
            activated += 1
    return {"ok": True, "activated": activated, "requested": len(rolls)}


# ============================================================================
# Feature flags (P4) + cost governance (P46) — admin-only
# ============================================================================
from app.services import cost_governance, flags  # noqa: E402


class FlagBody(_BM):
    enabled: bool


class BudgetBody(_BM):
    cohort: str
    monthly_usd: float = Field(ge=0)
    alert_pct: int = Field(default=80, ge=1, le=100)


@router.get("/flags")
async def get_flags(_: dict = Depends(require_admin)):
    return db.list_feature_flags()


@router.patch("/flags/{key}")
async def set_flag(key: str, body: FlagBody, admin: dict = Depends(require_admin)):
    updated = db.set_feature_flag(key, {"enabled": body.enabled})
    flags.invalidate()
    db.insert_entitlement_log(admin["user_id"], admin["user_id"], "set_flag",
                              int(body.enabled), key)
    return updated or {"ok": True}


@router.get("/budgets")
async def get_budgets(_: dict = Depends(require_admin)):
    """Cohort budgets + month-to-date spend evaluation (P46)."""
    return cost_governance.evaluate_all()


@router.put("/budgets")
async def put_budget(body: BudgetBody, admin: dict = Depends(require_admin)):
    db.upsert_cohort_budget(body.cohort, body.monthly_usd, body.alert_pct)
    db.insert_entitlement_log(admin["user_id"], admin["user_id"], "set_budget",
                              int(body.monthly_usd), body.cohort)
    return {"ok": True, "cohort": body.cohort}


@router.post("/budgets/enforce")
async def enforce_budgets(_: dict = Depends(require_admin)):
    """Manually run the throttle sweep (also runs nightly)."""
    return cost_governance.enforce()


@router.get("/usage-log")
async def usage_log(limit: int = 100, _: dict = Depends(require_admin)):
    """Recent per-request logs: who used which model and how many tokens (P7/P45).
    Admin-only — raw token integers are allowed here, never to students."""
    limit = max(1, min(limit, 500))
    try:
        rows = db.usage_log_latest(limit)
    except Exception:
        rows = []
    users = {u["id"]: u for u in db.list_users(limit=5000)}
    feed = []
    by_model: dict[str, dict] = {}
    total_tokens = total_cost = 0
    for r in rows:
        u = users.get(r["user_id"], {})
        p_tok = int(r.get("prompt_tokens") or 0)
        c_tok = int(r.get("completion_tokens") or 0)
        tot = p_tok + c_tok
        cost = float(r.get("cost_usd") or 0)
        total_tokens += tot
        total_cost += cost
        m = r.get("model") or "—"
        if m != "error":
            agg = by_model.setdefault(m, {"model": m, "requests": 0, "tokens": 0, "cost_usd": 0.0})
            agg["requests"] += 1
            agg["tokens"] += tot
            agg["cost_usd"] = round(agg["cost_usd"] + cost, 6)
        feed.append({
            "created_at": r.get("created_at"),
            "user": u.get("full_name") or u.get("email") or r["user_id"][:8],
            "email": u.get("email"),
            "model": m,
            "prompt_tokens": p_tok,
            "completion_tokens": c_tok,
            "total_tokens": tot,
            "cost_usd": round(cost, 6),
        })
    by_model_list = sorted(by_model.values(), key=lambda x: x["tokens"], reverse=True)
    return {
        "count": len(feed),
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 4),
        "by_model": by_model_list,
        "rows": feed,
    }


# --- Grant a specific plan to selected users (admin) -----------------------
class GrantPlanBody(_BM):
    user_ids: list[str] = Field(min_length=1)
    plan: str


@router.post("/grant-plan")
async def grant_plan(body: GrantPlanBody, admin: dict = Depends(require_admin)):
    """Activate selected users on a named plan (monthly/semester/annual …),
    setting expiry from the plan's duration and the plan's tier/cap."""
    plan = db.get_plan(body.plan)
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown plan: {body.plan}")
    expires = (datetime.now(timezone.utc)
               + timedelta(days=int(plan["duration_days"]))).isoformat()
    tier = plan.get("tier") or "normal"
    for uid in body.user_ids:
        patch = {"sub_status": "active", "sub_expires_at": expires, "plan": plan["code"]}
        if tier != "normal":   # pin non-default tiers (monthly/heavy) + their cap
            patch.update({"tier": tier, "tier_override": True,
                          "daily_cap": qp.cap_for_tier(tier)})
        db.update_user(uid, patch)
        db.insert_entitlement_log(admin["user_id"], uid, "grant_plan",
                                  int(plan["duration_days"]), plan["code"])
    return {"ok": True, "count": len(body.user_ids), "plan": plan["code"],
            "tier": tier, "expires_at": expires}


# ============================================================================
# Safety monitoring / safeguarding (admin oversight)
# Scope: campus plans only (semester / monthly). Annual "public" users are NOT
# viewable here and are not logged. Every chat view is recorded for audit.
# ============================================================================
class ReviewBody(_BM):
    notes: str | None = None


def _ensure_monitored(user_id: str) -> dict:
    u = db.get_user(user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if not safety.is_monitored(u):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This user is on the public (annual) plan and is not covered by "
            "campus monitoring.")
    return u


@router.get("/monitor/summary")
async def monitor_summary(_: dict = Depends(require_admin)):
    """Severity tallies for the monitoring dashboard header."""
    return db.safety_event_counts()


@router.get("/monitor/events")
async def monitor_events(severity: str | None = None, reviewed: str | None = None,
                         user_id: str | None = None, limit: int = 200,
                         _: dict = Depends(require_admin)):
    """Flagged jailbreak / safety events, newest first, enriched with the
    student's name + email for triage."""
    rev = True if reviewed in ("true", "1") else False if reviewed in ("false", "0") else None
    rows = db.list_safety_events(severity=severity or None, reviewed=rev,
                                 user_id=user_id or None, limit=limit)
    users = {u["id"]: u for u in db.list_users(limit=5000)}
    out = []
    for r in rows:
        u = users.get(r["user_id"], {})
        out.append({**r,
                    "user_name": u.get("full_name") or u.get("email") or r["user_id"][:8],
                    "user_email": u.get("email"),
                    "user_plan": u.get("plan")})
    return {"count": len(out), "events": out}


@router.post("/monitor/events/{event_id}/review")
async def monitor_review(event_id: str, body: ReviewBody,
                         admin: dict = Depends(require_admin)):
    updated = db.review_safety_event(event_id, admin["user_id"], body.notes)
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return updated


@router.get("/monitor/users/{user_id}/sessions")
async def monitor_user_sessions(user_id: str, _: dict = Depends(require_admin)):
    """List a monitored student's chat sessions (oversight)."""
    u = _ensure_monitored(user_id)
    return {
        "user": {"id": u["id"], "full_name": u.get("full_name"),
                 "email": u.get("email"), "plan": u.get("plan"),
                 "roll_no": u.get("roll_no")},
        "sessions": db.admin_list_sessions(user_id),
    }


@router.get("/monitor/users/{user_id}/sessions/{session_id}")
async def monitor_user_messages(user_id: str, session_id: str,
                                admin: dict = Depends(require_admin)):
    """Full transcript of a monitored student's session. The view itself is
    recorded in the entitlement log for accountability."""
    _ensure_monitored(user_id)
    sess = db.get_session(session_id, user_id)
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    db.insert_entitlement_log(admin["user_id"], user_id, "view_chat", 0, session_id)
    return {"session": sess, "messages": db.admin_get_messages(session_id, user_id)}
