"""Thin Supabase data-access layer.

The backend uses the *service-role* key, so it can read/write any row; tenant
isolation is enforced in code by always filtering on user_id. RLS in the DB is
a second line of defense.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.core.config import get_settings

settings = get_settings()


@lru_cache
def sb() -> Client:
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SERVICE_KEY not set. "
            "Create a Supabase project, run supabase/schema.sql, and fill .env."
        )
    return create_client(settings.supabase_url, settings.supabase_service_key)


# --- Users ------------------------------------------------------------------
def get_user_by_email(email: str) -> dict[str, Any] | None:
    r = sb().table("app_users").select("*").eq("email", email.lower()).limit(1).execute()
    return r.data[0] if r.data else None


def get_user(user_id: str) -> dict[str, Any] | None:
    r = sb().table("app_users").select("*").eq("id", user_id).limit(1).execute()
    return r.data[0] if r.data else None


def create_user(row: dict[str, Any]) -> dict[str, Any]:
    return sb().table("app_users").insert(row).execute().data[0]


def update_user(user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    return sb().table("app_users").update(patch).eq("id", user_id).execute().data[0]


def list_users(limit: int = 500) -> list[dict[str, Any]]:
    return sb().table("app_users").select("*").order("created_at", desc=True).limit(limit).execute().data


# --- Sessions / messages ----------------------------------------------------
def create_session(user_id: str, title: str, persona: str) -> dict[str, Any]:
    return sb().table("chat_sessions").insert(
        {"user_id": user_id, "title": title, "persona": persona}
    ).execute().data[0]


def list_sessions(user_id: str) -> list[dict[str, Any]]:
    return (sb().table("chat_sessions").select("*")
            .eq("user_id", user_id).order("updated_at", desc=True).execute().data)


def get_session(session_id: str, user_id: str) -> dict[str, Any] | None:
    r = (sb().table("chat_sessions").select("*")
         .eq("id", session_id).eq("user_id", user_id).limit(1).execute())
    return r.data[0] if r.data else None


def touch_session(session_id: str, title: str | None = None) -> None:
    patch: dict[str, Any] = {"updated_at": "now()"}
    if title:
        patch["title"] = title
    sb().table("chat_sessions").update(patch).eq("id", session_id).execute()


def delete_session(session_id: str, user_id: str) -> None:
    sb().table("chat_sessions").delete().eq("id", session_id).eq("user_id", user_id).execute()


def add_message(session_id: str, user_id: str, role: str, content: str,
                model: str | None = None, tokens: int = 0) -> dict[str, Any]:
    return sb().table("chat_messages").insert({
        "session_id": session_id, "user_id": user_id, "role": role,
        "content": content, "model": model, "tokens": tokens,
    }).execute().data[0]


def get_messages(session_id: str, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return (sb().table("chat_messages").select("*")
            .eq("session_id", session_id).eq("user_id", user_id)
            .order("created_at").limit(limit).execute().data)


# --- Memory (pgvector via RPC) ----------------------------------------------
def insert_memory(user_id: str, content: str, embedding: list[float],
                  kind: str = "note", source: str | None = None) -> None:
    sb().table("memory_chunks").insert({
        "user_id": user_id, "content": content, "embedding": embedding,
        "kind": kind, "source": source,
    }).execute()


def match_memory(user_id: str, query_embedding: list[float],
                 limit: int = 6, min_sim: float = 0.40) -> list[dict[str, Any]]:
    r = sb().rpc("match_memory", {
        "p_user_id": user_id, "p_query": query_embedding,
        "p_limit": limit, "p_min_sim": min_sim,
    }).execute()
    return r.data or []


# --- Shared institutional knowledge base (admin-uploaded, all users) --------
def insert_shared_memory(content: str, embedding: list[float],
                         source: str | None, uploaded_by: str) -> None:
    """Store a chunk in the institution-wide knowledge base. Visible to every
    user during retrieval (not scoped to one account)."""
    sb().table("memory_chunks").insert({
        "user_id": uploaded_by, "content": content, "embedding": embedding,
        "kind": "institution", "source": source,
        "shared": True, "verified": True,
    }).execute()


def match_shared_memory(query_embedding: list[float],
                        limit: int = 6, min_sim: float = 0.40) -> list[dict[str, Any]]:
    """Semantic search across the shared knowledge base (no user filter)."""
    r = sb().rpc("match_shared_memory", {
        "p_query": query_embedding, "p_limit": limit, "p_min_sim": min_sim,
    }).execute()
    return r.data or []


def list_shared_documents() -> list[dict[str, Any]]:
    """List shared-KB documents grouped by source filename, with chunk counts."""
    rows = (sb().table("memory_chunks").select("source,created_at")
            .eq("shared", True).execute().data) or []
    grouped: dict[str, dict] = {}
    for r in rows:
        src = r.get("source") or "(untitled)"
        g = grouped.setdefault(src, {"source": src, "chunks": 0, "created_at": r.get("created_at")})
        g["chunks"] += 1
        if r.get("created_at") and r["created_at"] < g["created_at"]:
            g["created_at"] = r["created_at"]
    return sorted(grouped.values(), key=lambda x: x["created_at"] or "", reverse=True)


def delete_shared_document(source: str) -> int:
    """Delete every shared chunk belonging to a source filename. Returns count."""
    existing = (sb().table("memory_chunks").select("id")
                .eq("shared", True).eq("source", source).execute().data) or []
    if existing:
        sb().table("memory_chunks").delete().eq("shared", True).eq("source", source).execute()
    return len(existing)


# --- Usage / metering -------------------------------------------------------
def log_usage(user_id: str, model: str, p_tokens: int, c_tokens: int, cost: float) -> None:
    sb().table("usage_log").insert({
        "user_id": user_id, "model": model,
        "prompt_tokens": p_tokens, "completion_tokens": c_tokens, "cost_usd": cost,
    }).execute()


def add_used_tokens(user_id: str, tokens: int) -> None:
    u = get_user(user_id)
    if u:
        sb().table("app_users").update(
            {"used_tokens": (u.get("used_tokens") or 0) + tokens}
        ).eq("id", user_id).execute()


def usage_summary(user_id: str) -> dict[str, Any]:
    rows = (sb().table("usage_log").select("prompt_tokens,completion_tokens,cost_usd")
            .eq("user_id", user_id).execute().data)
    return {
        "requests": len(rows),
        "tokens": sum((r["prompt_tokens"] + r["completion_tokens"]) for r in rows),
        "cost_usd": round(sum(float(r["cost_usd"]) for r in rows), 4),
    }


# --- Payments ---------------------------------------------------------------
def create_payment(row: dict[str, Any]) -> dict[str, Any]:
    return sb().table("payments").insert(row).execute().data[0]


def update_payment(rzp_order_id: str, patch: dict[str, Any]) -> None:
    sb().table("payments").update(patch).eq("rzp_order_id", rzp_order_id).execute()


# ============================================================================
# Epic B — quota / entitlements data access
# ============================================================================
def rpc_increment_daily_usage(user_id: str, tokens: int) -> int:
    r = sb().rpc("increment_daily_usage", {"p_user_id": user_id, "p_tokens": tokens}).execute()
    return r.data if isinstance(r.data, int) else 0


def rpc_bump_usage_daily(user_id: str, day: str, tokens: int, requests: int, hit_cap: bool) -> None:
    sb().rpc("bump_usage_daily", {
        "p_user_id": user_id, "p_day": day, "p_tokens": tokens,
        "p_requests": requests, "p_hit_cap": hit_cap,
    }).execute()


def rpc_claim_weekly_bonus(user_id: str, amount: int, reset_iso: str) -> bool:
    r = sb().rpc("claim_weekly_bonus", {
        "p_user_id": user_id, "p_amount": amount, "p_reset": reset_iso,
    }).execute()
    return bool(r.data)


def get_usage_daily(user_id: str, days: int = 14) -> list[dict]:
    return (sb().table("usage_daily").select("day,tokens,requests,hit_cap")
            .eq("user_id", user_id).order("day", desc=True).limit(days).execute().data)


def list_paid_users(limit: int = 5000) -> list[dict]:
    return (sb().table("app_users").select("*")
            .eq("role", "student").eq("sub_status", "active")
            .limit(limit).execute().data)


def insert_entitlement_log(actor_id: str | None, target_id: str, action: str,
                           delta: int = 0, detail: str | None = None) -> None:
    sb().table("entitlement_log").insert({
        "actor_user_id": actor_id, "target_user_id": target_id,
        "action": action, "delta": delta, "detail": detail,
    }).execute()


def get_entitlement_log(target_id: str, limit: int = 50) -> list[dict]:
    return (sb().table("entitlement_log").select("*")
            .eq("target_user_id", target_id).order("created_at", desc=True)
            .limit(limit).execute().data)


# ============================================================================
# Migration 003 — Epics A/C/D/E/G/H data access
# ============================================================================

# --- Auth tokens (email verify / password reset, P2) ------------------------
def insert_auth_token(user_id: str, kind: str, token_hash: str, expires_iso: str) -> None:
    sb().table("auth_tokens").insert({
        "user_id": user_id, "kind": kind,
        "token_hash": token_hash, "expires_at": expires_iso,
    }).execute()


def get_auth_token(token_hash: str, kind: str) -> dict[str, Any] | None:
    r = (sb().table("auth_tokens").select("*")
         .eq("token_hash", token_hash).eq("kind", kind)
         .eq("used", False).limit(1).execute())
    return r.data[0] if r.data else None


def consume_auth_token(token_id: str) -> None:
    sb().table("auth_tokens").update({"used": True}).eq("id", token_id).execute()


# --- Projects (P20 / P30) ---------------------------------------------------
def create_project(user_id: str, name: str, instructions: str | None = None,
                   color: str = "brand") -> dict[str, Any]:
    return sb().table("projects").insert({
        "user_id": user_id, "name": name,
        "instructions": instructions, "color": color,
    }).execute().data[0]


def list_projects(user_id: str) -> list[dict[str, Any]]:
    return (sb().table("projects").select("*")
            .eq("user_id", user_id).eq("archived", False)
            .order("updated_at", desc=True).execute().data)


def get_project(project_id: str, user_id: str) -> dict[str, Any] | None:
    r = (sb().table("projects").select("*")
         .eq("id", project_id).eq("user_id", user_id).limit(1).execute())
    return r.data[0] if r.data else None


def update_project(project_id: str, user_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    r = (sb().table("projects").update(patch)
         .eq("id", project_id).eq("user_id", user_id).execute())
    return r.data[0] if r.data else None


def delete_project(project_id: str, user_id: str) -> None:
    sb().table("projects").delete().eq("id", project_id).eq("user_id", user_id).execute()


# --- Session extras: project assignment, pin/archive, full-text search ------
def update_session(session_id: str, user_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    r = (sb().table("chat_sessions").update(patch)
         .eq("id", session_id).eq("user_id", user_id).execute())
    return r.data[0] if r.data else None


def list_sessions_in_project(user_id: str, project_id: str) -> list[dict[str, Any]]:
    return (sb().table("chat_sessions").select("*")
            .eq("user_id", user_id).eq("project_id", project_id)
            .order("updated_at", desc=True).execute().data)


def search_messages(user_id: str, query: str, limit: int = 30) -> list[dict[str, Any]]:
    return (sb().table("chat_messages")
            .select("session_id,role,content,created_at")
            .eq("user_id", user_id).ilike("content", f"%{query}%")
            .order("created_at", desc=True).limit(limit).execute().data)


# --- Memory: project scoping + listing (P30 / P31) --------------------------
def insert_memory_scoped(user_id: str, content: str, embedding: list[float],
                         kind: str = "note", source: str | None = None,
                         project_id: str | None = None) -> None:
    sb().table("memory_chunks").insert({
        "user_id": user_id, "content": content, "embedding": embedding,
        "kind": kind, "source": source, "project_id": project_id,
    }).execute()


def list_memory(user_id: str, project_id: str | None = None) -> list[dict[str, Any]]:
    q = (sb().table("memory_chunks").select("id,kind,source,content,project_id,created_at")
         .eq("user_id", user_id))
    if project_id:
        q = q.eq("project_id", project_id)
    return q.order("created_at", desc=True).limit(500).execute().data


def delete_memory(chunk_id: str, user_id: str) -> None:
    sb().table("memory_chunks").delete().eq("id", chunk_id).eq("user_id", user_id).execute()


# --- Message feedback + branching (P26) -------------------------------------
def set_message_feedback(message_id: str, user_id: str, feedback: int) -> None:
    (sb().table("chat_messages").update({"feedback": feedback})
     .eq("id", message_id).eq("user_id", user_id).execute())


# --- Share links (P27) ------------------------------------------------------
def create_share(token: str, session_id: str, user_id: str) -> None:
    sb().table("shared_chats").insert({
        "token": token, "session_id": session_id, "user_id": user_id,
    }).execute()


def get_share(token: str) -> dict[str, Any] | None:
    r = (sb().table("shared_chats").select("*")
         .eq("token", token).eq("revoked", False).limit(1).execute())
    return r.data[0] if r.data else None


def revoke_share(token: str, user_id: str) -> None:
    (sb().table("shared_chats").update({"revoked": True})
     .eq("token", token).eq("user_id", user_id).execute())


def list_shares(user_id: str) -> list[dict[str, Any]]:
    return (sb().table("shared_chats").select("*")
            .eq("user_id", user_id).eq("revoked", False)
            .order("created_at", desc=True).execute().data)


def get_messages_public(session_id: str) -> list[dict[str, Any]]:
    return (sb().table("chat_messages").select("role,content,model,created_at")
            .eq("session_id", session_id).order("created_at").execute().data)


def get_session_public(session_id: str) -> dict[str, Any] | None:
    r = sb().table("chat_sessions").select("id,title,persona").eq("id", session_id).limit(1).execute()
    return r.data[0] if r.data else None


# --- Plans & coupons (P16 / P18) --------------------------------------------
def list_plans() -> list[dict[str, Any]]:
    return (sb().table("plans").select("*").eq("active", True)
            .order("price_inr").execute().data)


def get_plan(code: str) -> dict[str, Any] | None:
    r = sb().table("plans").select("*").eq("code", code).limit(1).execute()
    return r.data[0] if r.data else None


def get_coupon(code: str) -> dict[str, Any] | None:
    r = sb().table("coupons").select("*").eq("code", code.upper()).eq("active", True).limit(1).execute()
    return r.data[0] if r.data else None


def redeem_coupon(code: str) -> None:
    c = get_coupon(code)
    if c:
        (sb().table("coupons").update({"redeemed": (c.get("redeemed") or 0) + 1})
         .eq("code", code.upper()).execute())


# --- Payments / billing history (P15 / P17) ---------------------------------
def get_payment_by_payment_id(rzp_payment_id: str) -> dict[str, Any] | None:
    r = (sb().table("payments").select("*")
         .eq("rzp_payment_id", rzp_payment_id).limit(1).execute())
    return r.data[0] if r.data else None


def list_payments(user_id: str) -> list[dict[str, Any]]:
    return (sb().table("payments").select("*")
            .eq("user_id", user_id).order("created_at", desc=True).execute().data)


def list_expired_active_users(now_iso: str, limit: int = 5000) -> list[dict[str, Any]]:
    return (sb().table("app_users").select("*")
            .eq("sub_status", "active").eq("role", "student")
            .lt("sub_expires_at", now_iso).limit(limit).execute().data)


# --- Analytics (P45, admin-only raw numbers) --------------------------------
def usage_daily_all(days_back_iso: str) -> list[dict[str, Any]]:
    return (sb().table("usage_daily").select("user_id,day,tokens,requests,hit_cap")
            .gte("day", days_back_iso).order("day").execute().data)


def usage_log_recent(since_iso: str, limit: int = 20000) -> list[dict[str, Any]]:
    return (sb().table("usage_log").select("user_id,model,prompt_tokens,completion_tokens,cost_usd,created_at")
            .gte("created_at", since_iso).limit(limit).execute().data)


# --- Privacy: export + delete (P41) -----------------------------------------
def export_user_data(user_id: str) -> dict[str, Any]:
    s = sb()
    user = get_user(user_id) or {}
    user.pop("password_hash", None)
    return {
        "profile": user,
        "sessions": s.table("chat_sessions").select("*").eq("user_id", user_id).execute().data,
        "messages": s.table("chat_messages").select("role,content,model,created_at,session_id").eq("user_id", user_id).execute().data,
        "memory": s.table("memory_chunks").select("kind,source,content,created_at").eq("user_id", user_id).execute().data,
        "projects": s.table("projects").select("*").eq("user_id", user_id).execute().data,
        "payments": s.table("payments").select("amount_inr,status,plan,created_at").eq("user_id", user_id).execute().data,
    }


def delete_user_account(user_id: str) -> None:
    # ON DELETE CASCADE handles sessions/messages/memory/projects/payments.
    sb().table("app_users").delete().eq("id", user_id).execute()


# ============================================================================
# Migration 004 — remaining phases data access (P3/P4/P24/P38/P46/P47/P50)
# ============================================================================

# --- OAuth / SSO (P3) -------------------------------------------------------
def get_user_by_provider_sub(provider: str, sub: str) -> dict[str, Any] | None:
    r = (sb().table("app_users").select("*")
         .eq("auth_provider", provider).eq("provider_sub", sub).limit(1).execute())
    return r.data[0] if r.data else None


# --- Feature flags (P4) -----------------------------------------------------
def list_feature_flags() -> list[dict[str, Any]]:
    return sb().table("feature_flags").select("*").order("key").execute().data


def get_feature_flag(key: str) -> dict[str, Any] | None:
    r = sb().table("feature_flags").select("*").eq("key", key).limit(1).execute()
    return r.data[0] if r.data else None


def set_feature_flag(key: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    patch = {**patch, "updated_at": "now()"}
    r = sb().table("feature_flags").update(patch).eq("key", key).execute()
    return r.data[0] if r.data else None


# --- Prompt library (P24) ---------------------------------------------------
def list_prompts(user_id: str) -> list[dict[str, Any]]:
    own = sb().table("prompts").select("*").eq("user_id", user_id).execute().data
    shared = sb().table("prompts").select("*").eq("shared", True).execute().data
    return shared + own


def create_prompt(user_id: str, slug: str, title: str, body: str) -> dict[str, Any]:
    return sb().table("prompts").insert({
        "user_id": user_id, "slug": slug, "title": title, "body": body,
    }).execute().data[0]


def delete_prompt(prompt_id: str, user_id: str) -> None:
    sb().table("prompts").delete().eq("id", prompt_id).eq("user_id", user_id).execute()


# --- Study aids (P38) -------------------------------------------------------
def create_study_aid(user_id: str, kind: str, title: str | None,
                     payload: dict, session_id: str | None = None) -> dict[str, Any]:
    return sb().table("study_aids").insert({
        "user_id": user_id, "kind": kind, "title": title,
        "payload": payload, "session_id": session_id,
    }).execute().data[0]


def list_study_aids(user_id: str) -> list[dict[str, Any]]:
    return (sb().table("study_aids").select("*")
            .eq("user_id", user_id).order("created_at", desc=True)
            .limit(100).execute().data)


def delete_study_aid(aid_id: str, user_id: str) -> None:
    sb().table("study_aids").delete().eq("id", aid_id).eq("user_id", user_id).execute()


# --- Cost governance: cohort budgets (P46) ----------------------------------
def list_cohort_budgets() -> list[dict[str, Any]]:
    return sb().table("cohort_budgets").select("*").order("cohort").execute().data


def upsert_cohort_budget(cohort: str, monthly_usd: float, alert_pct: int) -> dict[str, Any]:
    return sb().table("cohort_budgets").upsert({
        "cohort": cohort, "monthly_usd": monthly_usd,
        "alert_pct": alert_pct, "updated_at": "now()",
    }).execute().data[0]


def set_cohort_throttle(cohort: str, throttled: bool) -> None:
    (sb().table("cohort_budgets").update({"throttled": throttled, "updated_at": "now()"})
     .eq("cohort", cohort).execute())


def get_cohort_budget(cohort: str) -> dict[str, Any] | None:
    r = sb().table("cohort_budgets").select("*").eq("cohort", cohort).limit(1).execute()
    return r.data[0] if r.data else None


def cohort_spend_since(cohort: str, since_iso: str) -> float:
    members = (sb().table("app_users").select("id").eq("cohort", cohort).execute().data)
    ids = [m["id"] for m in members]
    if not ids:
        return 0.0
    rows = (sb().table("usage_log").select("user_id,cost_usd")
            .gte("created_at", since_iso).in_("user_id", ids).execute().data)
    return round(sum(float(r.get("cost_usd") or 0) for r in rows), 4)


# --- Reliability: incidents / status (P47) ----------------------------------
def list_incidents(limit: int = 20) -> list[dict[str, Any]]:
    return (sb().table("incidents").select("*")
            .order("created_at", desc=True).limit(limit).execute().data)


def list_open_incidents() -> list[dict[str, Any]]:
    return (sb().table("incidents").select("*")
            .neq("status", "resolved").order("created_at", desc=True).execute().data)


def create_incident(title: str, severity: str, body: str | None) -> dict[str, Any]:
    return sb().table("incidents").insert({
        "title": title, "severity": severity, "body": body,
    }).execute().data[0]


def update_incident(incident_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    r = sb().table("incidents").update(patch).eq("id", incident_id).execute()
    return r.data[0] if r.data else None


# --- Pilot feedback + NPS (P50) ---------------------------------------------
def create_feedback(user_id: str, kind: str, score: int | None,
                    comment: str | None, context: str | None) -> dict[str, Any]:
    return sb().table("feedback_responses").insert({
        "user_id": user_id, "kind": kind, "score": score,
        "comment": comment, "context": context,
    }).execute().data[0]


def list_feedback(kind: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
    q = sb().table("feedback_responses").select("*")
    if kind:
        q = q.eq("kind", kind)
    return q.order("created_at", desc=True).limit(limit).execute().data


# --- Branching: fork a session at a point (P26) ------------------------------
def fork_session(session_id: str, user_id: str, upto_message_id: str | None = None,
                 new_title: str | None = None) -> dict[str, Any] | None:
    """Create a new session copying messages up to (and including) a given
    message id, so the user can edit/branch from there. parent linkage is the
    new session's project_id-independent title prefix 'Branch of …'."""
    src = get_session(session_id, user_id)
    if not src:
        return None
    msgs = get_messages(session_id, user_id, limit=500)
    cutoff_reached = upto_message_id is None
    copied: list[dict] = []
    for m in msgs:
        copied.append(m)
        if upto_message_id and m.get("id") == upto_message_id:
            cutoff_reached = True
            break
    if upto_message_id and not cutoff_reached:
        copied = msgs  # id not found → copy all
    title = new_title or f"Branch of {src.get('title', 'chat')}"[:80]
    new = create_session(user_id, title, src.get("persona", "kgpt"))
    for m in copied:
        if m.get("role") in ("user", "assistant"):
            add_message(new["id"], user_id, m["role"], m["content"], model=m.get("model"))
    return new


# --- Admin usage log feed (per-request model + tokens) ----------------------
def usage_log_latest(limit: int = 200) -> list[dict[str, Any]]:
    return (sb().table("usage_log")
            .select("user_id,model,prompt_tokens,completion_tokens,cost_usd,created_at")
            .order("created_at", desc=True).limit(limit).execute().data)


# ============================================================================
# Migration 007 — Safety monitoring / safeguarding (admin oversight)
# ============================================================================
def insert_safety_event(user_id: str, session_id: str | None, severity: str,
                        category: str, score: int, blocked: bool,
                        snippet: str | None, reasons: str | None) -> dict[str, Any] | None:
    try:
        r = sb().table("safety_events").insert({
            "user_id": user_id, "session_id": session_id, "severity": severity,
            "category": category, "score": score, "blocked": blocked,
            "snippet": snippet, "reasons": reasons,
        }).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None  # logging must never break a chat request


def list_safety_events(severity: str | None = None, reviewed: bool | None = None,
                       user_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    q = sb().table("safety_events").select("*")
    if severity:
        q = q.eq("severity", severity)
    if reviewed is not None:
        q = q.eq("reviewed", reviewed)
    if user_id:
        q = q.eq("user_id", user_id)
    return q.order("created_at", desc=True).limit(max(1, min(limit, 1000))).execute().data


def get_safety_event(event_id: str) -> dict[str, Any] | None:
    r = sb().table("safety_events").select("*").eq("id", event_id).limit(1).execute()
    return r.data[0] if r.data else None


def review_safety_event(event_id: str, admin_id: str, notes: str | None) -> dict[str, Any] | None:
    patch = {"reviewed": True, "reviewed_by": admin_id,
             "reviewed_at": "now()", "notes": notes}
    r = sb().table("safety_events").update(patch).eq("id", event_id).execute()
    return r.data[0] if r.data else None


def safety_event_counts() -> dict[str, int]:
    """Lightweight severity tallies for the monitoring dashboard header."""
    rows = (sb().table("safety_events").select("severity,reviewed,blocked")
            .limit(5000).execute().data)
    out = {"total": len(rows), "high": 0, "medium": 0, "low": 0,
           "unreviewed": 0, "blocked": 0}
    for r in rows:
        out[r.get("severity", "low")] = out.get(r.get("severity", "low"), 0) + 1
        if not r.get("reviewed"):
            out["unreviewed"] += 1
        if r.get("blocked"):
            out["blocked"] += 1
    return out


def admin_list_sessions(user_id: str) -> list[dict[str, Any]]:
    """Admin-side: list a specific user's sessions (oversight). Caller must
    authorize (require_admin + monitored-plan check) before calling this."""
    return list_sessions(user_id)


def admin_get_messages(session_id: str, user_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    """Admin-side: full message history for a user's session."""
    return get_messages(session_id, user_id, limit=limit)
