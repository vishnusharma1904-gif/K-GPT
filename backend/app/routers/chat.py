"""Chat — per-user sessions, RAG memory, tiered-quota metered, streaming + sync.

Epic B request lifecycle:
    moderation.screen_input  # safety (fail soft, no model call if blocked)
    refresh(user)            # lazy daily/weekly reset
    fairuse.check_rate       # per-minute limit
    check_access(user)       # tier cap / subscription / suspension
    [concurrency guard]      # per-user in-flight cap
    should_downshift         # near cap -> cheapest models
    ... model call ...
    record_usage             # atomic metering

Behaviour layers (Epic D/E/G): persona + response style + custom instructions
(P25), academic-integrity overlay (P40), memory RAG with citations (P31/P32),
optional web search grounding (P33), per-project instructions + knowledge (P30).
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.security import current_user
from app.db import supabase_client as db
from app.db import queue_client
from app.schemas import ChatReq, FeedbackReq, NewSessionReq, SessionPatch
from app.services import quota_policy as qp
from app.services import (auto_memory, embeddings, entitlements, fairuse,
                          moderation, prompt_guard, prompting, rag, safety,
                          smalltalk, smart_router, topic, websearch)

settings = get_settings()
router = APIRouter(prefix="/api/chat", tags=["chat"])
HISTORY_TURNS = 10
# Cap the conversation history fed to the model. Old turns are dropped oldest-first
# once this character budget is hit — keeps prompt tokens (and cost) bounded on
# long sessions instead of resending the entire transcript every turn.
HISTORY_CHAR_BUDGET = 6000


def _trim_history(history: list[dict]) -> list[dict]:
    """Keep the most recent user/assistant turns within HISTORY_CHAR_BUDGET,
    preserving chronological order."""
    kept: list[dict] = []
    budget = HISTORY_CHAR_BUDGET
    for m in reversed(history):
        if m.get("role") not in ("user", "assistant"):
            continue
        content = m.get("content") or ""
        if kept and budget - len(content) < 0:
            break
        budget -= len(content)
        kept.append({"role": m["role"], "content": content})
    kept.reverse()
    return kept

import hashlib
from app.db import redis_client

_SYS_PROMPT_VERSION = "v1"
_KB_VERSION = "v1"
_MODELS_VERSION = "v8"
_ROUTING_VERSION = "v8"

def _exact_cache_key(question: str, mode: str) -> str:
    raw = f"{question}|{mode}|{_SYS_PROMPT_VERSION}|{_KB_VERSION}|{_MODELS_VERSION}|{_ROUTING_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()

_MODE_TTLS = {
    "general": 30 * 86400,
    "lifestyle": 14 * 86400,
    "education": 7 * 86400,
    "medical": 86400,
    "personal": 0
}


def _cache_eligible(user: dict, req: ChatReq, had_context: bool) -> bool:
    """Whether a request may be answered from / written to the semantic cache.

    Only fully generic, non-personalised questions qualify, so a cached answer is
    always a safe, correct response to the question alone — never leaking one
    user's context to another."""
    if had_context:
        return False
    if req.images or req.web_search or req.project_id or getattr(req, "strict", False):
        return False
    if getattr(req, "model", None) or getattr(req, "premium", False):
        return False
    if user.get("custom_instructions") or user.get("exam_mode"):
        return False
    persona = (req.persona or "").strip().lower()
    if persona and persona not in ("default", "general"):
        return False
    # Self-referential questions ("what's my name", "who am I", "what do I
    # like") are answered from the always-on profile block (auto_memory
    # facts), NOT from `had_context` — so they'd otherwise pass every check
    # above even though the correct answer changes as memory updates. The
    # semantic cache has no per-user scoping, so caching these risks BOTH
    # serving a stale answer after the user corrects a fact AND leaking one
    # user's personal answer to a different user who phrases things similarly.
    if auto_memory.looks_personal(req.message):
        return False
    return True


def _load_user(claims: dict) -> dict:
    u = db.get_user(claims["user_id"])
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return u


def _queue_memory(user: dict, message: str, session_id: str | None) -> None:
    """Best-effort: hand the message to the Prompt Pulse worker for durable,
    cross-restart fact extraction into Qdrant. No-op when RabbitMQ isn't
    configured, so it never adds latency or breaks the request in deployments
    still on the in-process auto_memory path."""
    if user.get("memory_enabled", True):
        try:
            queue_client.publish_memory_extract(user["id"], message, session_id)
        except Exception:
            pass


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


def _prepare(claims: dict, request: Request, premium: bool):
    """Shared pre-flight for both chat endpoints. Returns (user, allow_premium)."""
    user = _load_user(claims)
    is_admin = user.get("role") == "admin"
    # Faculty are privileged (no student rate/quota), but still must verify email.
    privileged = user.get("role") in ("admin", "faculty")
    fairuse.check_rate(user["id"], privileged)
    fairuse.note_ip(user["id"], _client_ip(request))      # anomaly tracking (best-effort)
    user = entitlements.refresh(user)                      # lazy resets
    entitlements.check_access(user)                        # tier cap / sub / suspend
    if (settings.require_email_verification and not is_admin
            and not user.get("email_verified")):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Please verify your email to start chatting. Check your inbox.")
    allow_premium = bool(premium) and (
        settings.premium_models_for_students or is_admin)
    return user, allow_premium


_PICKABLE = {"instant", "fast_chat", "reasoning", "coding", "multilingual",
             "long_context", "rag", "premium", "education", "medical", "lifestyle", "general", "personal"}


def _can_pick_model(user: dict) -> bool:
    """Model picking is reserved for power hitters (Heavy tier) and admins."""
    return user.get("role") == "admin" or user.get("tier") == "heavy"


def _chosen_model(user: dict, req: ChatReq) -> str | None:
    if req.model and _can_pick_model(user):
        valid = {m["id"] for m in smart_router.selectable_models()}
        if req.model in valid:
            return req.model
    return None


# Bengali through Malayalam (U+0980-U+0D7F) covers Telugu, Tamil, Kannada,
# Malayalam, Bengali, Gurmukhi/Punjabi, Gujarati, and Odia — the Indic
# languages NOT on the free Groq models' (Llama 3.1 8B, Gemma2 9B) official
# supported-language list. Devanagari (Hindi, U+0900-U+097F) is deliberately
# EXCLUDED: Hindi already works well on the free models, so there's no reason
# to spend paid credits on it. When this matches, the "multilingual" mode
# chain (Qwen3.5-9B first, free models as graceful fallback — see models.json)
# is used instead of "general", so the paid model is only ever reached for
# messages that actually need it.
_WEAK_SUPPORT_SCRIPT = re.compile(r"[ঀ-ൿ]")


def _needs_multilingual_fallback(message: str) -> bool:
    return bool(_WEAK_SUPPORT_SCRIPT.search(message or ""))


# Output is no longer capped per request — a user may spend their whole daily
# budget in one go. We instead *estimate* the cost up front and caution them.
_BIG_OUTPUT = ("website", "web page", "webpage", "full code", "entire", "complete",
               "implement", "build", "generate a", "application", "app ", "essay",
               "document", "report", "article", "detailed", "comprehensive",
               "boilerplate", "project", "dashboard", "landing page", "portfolio")
_CODE_HINTS = ("code", "function", "class ", "script", "html", "css", "python",
               "java", "react", "api", "sql", "algorithm")


def _estimate_completion_tokens(message: str) -> int:
    """Rough guess of how many tokens the answer will use (approx, for warning)."""
    m = message.lower()
    est = 500
    if any(k in m for k in _BIG_OUTPUT):
        est += 6000
    if any(k in m for k in _CODE_HINTS):
        est += 2500
    # explicit length asks
    if "in detail" in m or "step by step" in m or "thorough" in m:
        est += 1500
    return min(est, 16000)


def _estimate_cost(user: dict, message: str, history_chars: int) -> dict:
    """Return ONLY percentages (no raw tokens) so the %-only contract holds."""
    prompt_tokens = (len(message) + history_chars) // 4 + 250  # +system overhead
    completion_tokens = _estimate_completion_tokens(message)
    total = prompt_tokens + completion_tokens
    eff = entitlements._effective_cap(user) or 1
    pct = round(total / eff * 100, 1)
    used = qp.percent_used(user.get("daily_used") or 0, eff)
    remaining = max(0.0, round(100 - used, 1))
    if pct >= 25 or pct > remaining:
        level = "high"
    elif pct >= 8:
        level = "medium"
    else:
        level = "low"
    return {"percent": pct, "remaining_percent": remaining,
            "exceeds": pct > remaining, "level": level,
            "warn": pct >= 10}   # only caution above ~10% of the daily cap


def _category(user: dict, message: str, allow_premium: bool,
              requested: str | None = None, has_images: bool = False) -> str:
    # Images must route to a vision-capable model regardless of other signals (P34).
    if has_images:
        return "vision"
    # Near the cap, downshift to the cheapest category to stretch the budget.
    if entitlements.should_downshift(user):
        return "instant"
    if allow_premium:
        return "premium"
    if requested and requested in _PICKABLE:
        return requested            # P21 user-chosen category
    return topic.classify(message)


async def _build_messages(user: dict, req: ChatReq) -> tuple[list[dict], list[dict], dict]:
    """Assemble model messages + citations + a meta dict.

    meta = {"vec": <query embedding or None>, "had_context": bool}. The query is
    embedded at most once here and reused for both retrieval and the semantic
    cache (in the endpoints), so we never pay for the same embedding twice.
    """
    citations: list[dict] = []
    project = None
    if req.project_id:
        project = db.get_project(req.project_id, user["id"])

    # --- memory + document RAG (Qdrant-first, pgvector fallback) ---
    memory_ctx = None
    query_vec: list[float] | None = None
    strict = bool(req.strict)
    # Strict (KB-only) mode always retrieves both the user's documents and the
    # shared KB, regardless of the personal-memory toggle, because the whole point
    # is to ground the answer in those documents.
    want_memory = strict or (req.use_memory and user.get("memory_enabled", True))
    # Don't search the knowledge base for pure chit-chat (greetings, thanks, byes,
    # "hi hello", etc.). These add cost/latency and pollute non-educational replies
    # with irrelevant document context. Strict mode is exempt — it must always
    # ground in the KB. (Exact greetings are already short-circuited to a canned
    # reply before this; this also covers the looser/non-exact casual messages.)
    casual = (not strict) and smalltalk.is_smalltalk(req.message)
    # Topic of the message (edu/tech/medical/lifestyle/personal/greeting/other).
    # Used to skip the shared KB for clearly non-academic messages and as a tag.
    from app.services import topic as _topic
    classification = _topic.classify(req.message)
    msg_topic = classification.mode
    use_shared_kb = strict or _topic.should_use_kb(msg_topic)
    # The institution-wide shared KB is served to every user (it is not personal
    # data), so retrieval is gated on `retrieval_possible()` — NOT the personal
    # memory toggle. Personal documents/memory remain gated on `want_memory`.
    want_retrieval = (want_memory or rag.retrieval_possible()) and not casual
    # Embed once if we need retrieval or could use the semantic cache. Skipped for
    # casual messages so they never trigger a vector search at all.
    if (want_retrieval or rag.qdrant_enabled()) and not casual:
        try:
            query_vec = rag.embed_query(req.message)
        except Exception:
            query_vec = None
    # Per-cohort shared KB: a student only retrieves docs targeted to their
    # branch / current year / section (or to "Everyone"). Faculty & admin are
    # unscoped (scope=None) so they search the whole shared KB.
    from app.services import cohort as _cohort_scope
    _priv = user.get("role") in ("admin", "faculty")
    _scope_year = _cohort_scope.derive(user.get("admission_year"), user.get("course"))[0]
    shared_scope = None if _priv else {
        "branch": user.get("branch"), "year": _scope_year, "section": user.get("section"),
    }
    if want_retrieval and query_vec is not None:
        try:
            # If a file is explicitly attached, disable general RAG search across the entire KB
            # and other documents to prevent irrelevant documents from polluting the context.
            inc_personal = want_memory and not bool(req.attached_source)
            inc_shared = use_shared_kb and not bool(req.attached_source)
            
            lines, mem_citations = rag.retrieve(
                user["id"], req.message, query_vec, project_id=req.project_id,
                include_personal=inc_personal, include_shared=inc_shared,
                shared_scope=shared_scope)
            if lines:
                citations.extend(mem_citations)
                memory_ctx = "\n".join(lines)
        except Exception:
            pass

    # A file the user EXPLICITLY attached in the composer is force-injected here
    # (by filename, no similarity threshold) and placed FIRST, so the model always
    # sees it — fixes "no file is attached" on summarise/convert-style requests.
    if req.attached_source:
        try:
            a_lines, a_cits = rag.attached_context(user["id"], req.attached_source)
            if a_lines:
                citations = a_cits + citations
                memory_ctx = "\n".join(a_lines + ([memory_ctx] if memory_ctx else []))
        except Exception:
            pass

    # --- optional web search grounding (P33) ---
    # Strict mode is KB-only, so web search is force-disabled there.
    web_ctx = ""
    if req.web_search and not strict:
        results = await websearch.search(req.message, k=4)
        # External text is untrusted → strip obvious injected override lines.
        web_ctx = moderation.sanitize_untrusted(websearch.format_context(results))
        for i, r in enumerate(results, 1):
            citations.append({"type": "web", "n": i, "title": r["title"],
                              "url": r["url"], "snippet": r.get("snippet", "")})

    # Memory may contain text extracted from uploaded files → also untrusted.
    if memory_ctx:
        memory_ctx = moderation.sanitize_untrusted(memory_ctx)

    combined_ctx = "\n\n".join(c for c in (memory_ctx, web_ctx) if c) or None

    # --- Learned-answer reuse: pull RELATED past answers so the model reuses the
    #     overlapping part (e.g. a definition already answered for someone else)
    #     and only generates the new part. Disabled in strict (KB-docs-only) mode.
    #     Deliberately NOT counted as had_context, so the fuller new answer is
    #     still cached for future reuse.
    learned_ctx = None
    if not strict and query_vec is not None:
        try:
            learned = rag.retrieve_learned(query_vec)
            if learned:
                learned_ctx = moderation.sanitize_untrusted("\n".join(learned))
        except Exception:
            pass

    name = (user.get("full_name") or "").split(" ")[0] or None
    profile = auto_memory.profile_block(user["id"]) if user.get("memory_enabled", True) else None
    is_admin = user.get("role") == "admin"
    # Cohort line from the student's profile. Year + semester are DERIVED from
    # admission_year + today's date so they advance automatically over time.
    from app.services import cohort as _cohort
    _cy, _cs = _cohort.derive(user.get("admission_year"), user.get("course"))
    _bits = []
    if user.get("course"): _bits.append(str(user["course"]))
    if user.get("branch"): _bits.append(str(user["branch"]))
    if _cy: _bits.append(f"Year {_cy}")
    if _cs: _bits.append("Odd semester" if _cs == 1 else "Even semester")
    if user.get("section"): _bits.append(f"Section {user['section']}")
    cohort = (", ".join(_bits) + ".") if _bits else None
    sys = prompting.build_system_prompt(
        persona=req.persona,
        student_name=name,
        response_style=user.get("response_style"),
        custom_instructions=user.get("custom_instructions"),
        exam_mode=bool(user.get("exam_mode")),
        memory_context=combined_ctx,
        has_untrusted_docs=bool(req.web_search or memory_ctx),
        user_profile=profile,
        cohort=cohort,
        is_admin=is_admin,
        strict=strict,
        learned_context=learned_ctx,
        mode=msg_topic,
    )
    if project and project.get("instructions"):
        sys += f"\n\nProject context — {project['name']}:\n{project['instructions']}"

    msgs = [{"role": "system", "content": sys}]
    if req.session_id:
        history = db.get_messages(req.session_id, user["id"], limit=HISTORY_TURNS * 2)
        msgs.extend(_trim_history(history))   # bounded by HISTORY_CHAR_BUDGET
    if req.images:
        # P34 vision: OpenAI/LiteLLM multimodal content parts.
        parts: list[dict] = [{"type": "text", "text": req.message}]
        for url in req.images[:4]:
            parts.append({"type": "image_url", "image_url": {"url": url}})
        msgs.append({"role": "user", "content": parts})
    else:
        msgs.append({"role": "user", "content": req.message})

    meta = {"vec": query_vec, "had_context": bool(memory_ctx or web_ctx),
            "topic": msg_topic, "classification": classification}
    return msgs, citations, meta


# --- Session CRUD -----------------------------------------------------------
@router.get("/sessions")
async def sessions(project_id: str | None = None, claims: dict = Depends(current_user)):
    if project_id:
        return db.list_sessions_in_project(claims["user_id"], project_id)
    return db.list_sessions(claims["user_id"])


@router.post("/sessions")
async def new_session(req: NewSessionReq, claims: dict = Depends(current_user)):
    s = db.create_session(claims["user_id"], req.title, req.persona)
    if req.project_id:
        db.update_session(s["id"], claims["user_id"], {"project_id": req.project_id})
    return s


@router.get("/sessions/{session_id}")
async def history(session_id: str, claims: dict = Depends(current_user)):
    if not db.get_session(session_id, claims["user_id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return db.get_messages(session_id, claims["user_id"])


@router.patch("/sessions/{session_id}")
async def patch_session(session_id: str, body: SessionPatch, claims: dict = Depends(current_user)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        return {"ok": True}
    updated = db.update_session(session_id, claims["user_id"], patch)
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return updated


@router.delete("/sessions/{session_id}")
async def remove_session(session_id: str, claims: dict = Depends(current_user)):
    db.delete_session(session_id, claims["user_id"])
    return {"ok": True}


class BranchReq(BaseModel):
    message_id: str | None = None     # fork up to and including this message
    title: str | None = None


@router.post("/sessions/{session_id}/branch")
async def branch_session(session_id: str, body: BranchReq,
                         claims: dict = Depends(current_user)):
    """Edit-and-branch (P26): fork a conversation into a new session so an
    alternate path can be explored without losing the original."""
    new = db.fork_session(session_id, claims["user_id"], body.message_id, body.title)
    if not new:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return new


@router.get("/search")
async def search(q: str, claims: dict = Depends(current_user)):
    if not q.strip():
        return []
    return db.search_messages(claims["user_id"], q.strip())


@router.get("/models")
async def list_models(claims: dict = Depends(current_user)):
    """Concrete models a paid/admin user can pin (Phase 21 model picker)."""
    user = db.get_user(claims["user_id"])
    return {"can_pick": bool(user and _can_pick_model(user)),
            "models": smart_router.selectable_models()}


class EstimateReq(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None


@router.post("/estimate")
async def estimate(body: EstimateReq, claims: dict = Depends(current_user)):
    """Approximate how much of today's limit a prompt will consume, as a %.
    Returns percentages only (no raw token counts) — admins read 'unlimited'."""
    user = db.get_user(claims["user_id"])
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.get("role") == "admin":
        return {"percent": 0.0, "remaining_percent": 100.0, "exceeds": False,
                "level": "low", "unlimited": True}
    user = entitlements.refresh(user)
    history_chars = 0
    if body.session_id and db.get_session(body.session_id, user["id"]):
        for m in db.get_messages(body.session_id, user["id"], limit=20):
            history_chars += len(m.get("content") or "")
    return _estimate_cost(user, body.message, history_chars)


@router.post("/feedback")
async def feedback(body: FeedbackReq, claims: dict = Depends(current_user)):
    db.set_message_feedback(body.message_id, claims["user_id"], body.feedback)
    return {"ok": True}


# --- Chat (non-streaming) ---------------------------------------------------
@router.post("")
async def chat(req: ChatReq, request: Request, claims: dict = Depends(current_user)):
    user, allow_premium = _prepare(claims, request, req.premium)

    verdict = moderation.screen_input(req.message)
    ev = safety.assess(req.message, None if verdict.allowed else verdict.category)
    if safety.is_monitored(user) and ev.loggable:
        db.insert_safety_event(user["id"], req.session_id, ev.severity, ev.category,
                               ev.score, (not verdict.allowed) or ev.blocked,
                               safety.snippet(req.message), "; ".join(ev.reasons) or None)
    if not verdict.allowed:
        return {"session_id": req.session_id, "reply": verdict.message,
                "model": "moderation", "category": "blocked", "blocked": True,
                "usage": entitlements.usage_view(user), "citations": []}
    if ev.blocked:
        return {"session_id": req.session_id, "reply": safety.JAILBREAK_REFUSAL,
                "model": "safety", "category": "blocked", "blocked": True,
                "usage": entitlements.usage_view(user), "citations": []}

    session_id = req.session_id
    if not session_id:
        title = req.message[:48] + ("…" if len(req.message) > 48 else "")
        s = db.create_session(user["id"], title, req.persona)
        session_id = s["id"]
        if req.project_id:
            db.update_session(session_id, user["id"], {"project_id": req.project_id})
        req.session_id = session_id

    # --- Instant canned reply for greetings / identity small-talk (no LLM) ---
    canned = None if req.images else smalltalk.match(req.message)
    if canned:
        db.add_message(session_id, user["id"], "user", req.message)
        db.add_message(session_id, user["id"], "assistant", canned,
                       model="kgpt-smalltalk", tokens=0)
        db.touch_session(session_id)
        return {
            "session_id": session_id, "reply": canned, "model": "kgpt-smalltalk",
            "category": "smalltalk", "citations": [],
            "usage": entitlements.usage_view(user),
        }

    msgs, citations, meta = await _build_messages(user, req)
    classification = meta["classification"]
    chosen = _chosen_model(user, req)
    # Routed through a dedicated chain (Qwen3.5-9B first, free Groq/Zenmux
    # models as graceful fallback if it errors) rather than a hard single-model
    # override — used ONLY when the message needs language support the free
    # models lack (see _needs_multilingual_fallback), never as a default, and
    # never for explicit picks or vision (own chain).
    force_multilingual = (not chosen and not req.images
                          and _needs_multilingual_fallback(req.message))
    if chosen:
        mode, intent_str = "custom", "custom"
    else:
        if force_multilingual:
            mode, intent_str = "multilingual", "multilingual"
        elif bool(req.images):
            mode, intent_str = "vision", "vision"
        elif entitlements.should_downshift(user):
            mode, intent_str = "general", "instant"
        elif allow_premium:
            mode, intent_str = "premium", "premium"
        elif req.category and req.category in _PICKABLE:
            mode, intent_str = req.category, req.category
        else:
            mode, intent_str = classification.mode, classification.intent

    # --- Exact Match Redis Cache (0 tokens, 1ms) ---
    eligible = _cache_eligible(user, req, meta["had_context"])
    ttl = _MODE_TTLS.get(mode, 0)
    
    if eligible and ttl > 0:
        cache_key = _exact_cache_key(req.message, mode)
        hit = redis_client.cache_get_json("exact", cache_key)
        if hit and hit.get("response"):
            reply_text = hit["response"]
            db.add_message(session_id, user["id"], "user", req.message)
            db.add_message(session_id, user["id"], "assistant", reply_text,
                           model=hit.get("model", "exact_cache"), tokens=0)
            db.touch_session(session_id)
            auto_memory.schedule(user["id"], req.message, user.get("memory_enabled", True))
            return {
                "session_id": session_id,
                "reply": reply_text,
                "model": hit.get("model", "exact_cache"),
                "category": mode,
                "citations": [],
                "usage": entitlements.usage_view(user),
                "cached": True,
            }

    # --- Semantic cache: a near-identical generic question skips the LLM ---
    # Gated on ttl (not just `eligible`) so "personal" topic messages (ttl=0 —
    # e.g. "what's my name") never serve a frozen cached answer that ignores
    # the user's current memory/profile facts.
    if eligible and ttl > 0 and meta["vec"] is not None:
        hit = rag.cache_lookup(meta["vec"])
        if hit and hit.get("response"):
            reply_text = hit["response"]
            db.add_message(session_id, user["id"], "user", req.message)
            db.add_message(session_id, user["id"], "assistant", reply_text,
                           model=hit.get("model", "cache"), tokens=0)
            db.touch_session(session_id)
            auto_memory.schedule(user["id"], req.message, user.get("memory_enabled", True))
            return {
                "session_id": session_id,
                "reply": reply_text,
                "model": hit.get("model", "cache"),
                "category": mode,
                "citations": [],
                "usage": entitlements.usage_view(user),
                "cached": True,
            }

    p_tok = sum(len(m.get("content", "")) if isinstance(m.get("content", ""), str) else sum(len(part.get("text", "")) for part in m.get("content", []) if isinstance(part, dict)) for m in msgs) // 4
    caps = {}
    if req.attached_source or p_tok > 15000:
        caps["long_context"] = True
    if req.images:
        # Vision requests must only fall back to vision-capable models — otherwise
        # a non-vision model can silently land at the end of the chain and either
        # error or hallucinate about content it never received.
        caps["vision"] = True

    with fairuse.concurrency(user["id"], user.get("role") == "admin"):
        result = await smart_router.complete(msgs, mode=mode, intent=intent_str, capabilities_required=caps, temperature=0.7, model=chosen)

    # Output-side guard: never return (or store) a reply that leaked the system
    # prompt / canary or signalled a successful jailbreak.
    reply_text = result["text"]
    if not moderation.screen_output(reply_text).allowed:
        reply_text = prompt_guard.OUTPUT_REDACTION
        if safety.is_monitored(user):
            db.insert_safety_event(user["id"], session_id, "high", "prompt_leak", 90,
                                   True, safety.snippet(req.message), "output leak blocked")

    db.add_message(session_id, user["id"], "user", req.message)
    db.add_message(session_id, user["id"], "assistant", reply_text,
                   model=result["model"], tokens=result["completion_tokens"],
                   prompt_tokens=result.get("prompt_tokens", 0), cost_usd=result.get("cost_usd", 0.0))
    db.touch_session(session_id)
    entitlements.record_usage(user["id"], result["model"],
                              result["prompt_tokens"], result["completion_tokens"],
                              result["cost_usd"])
    auto_memory.schedule(user["id"], req.message, user.get("memory_enabled", True))
    _queue_memory(user, req.message, session_id)

    # Cache only generic, non-personalised answers that passed the output guard.
    if eligible and reply_text != prompt_guard.OUTPUT_REDACTION:
        if ttl > 0:
            redis_client.cache_set_json("exact", _exact_cache_key(req.message, mode), 
                                        {"response": reply_text, "model": result["model"]}, ttl)
        if ttl > 0 and meta["vec"] is not None:
            rag.cache_store(meta["vec"], reply_text, result["model"], question=req.message)

    usage = entitlements.usage_view(db.get_user(user["id"]))  # percentage only
    return {
        "session_id": session_id,
        "reply": reply_text,
        "model": result["model"],
        "category": mode,
        "topic": meta.get("topic"),
        "citations": citations,
        "usage": usage,
        "prompt_tokens": result.get("prompt_tokens", 0),
        "completion_tokens": result.get("completion_tokens", 0),
        "cost_usd": result.get("cost_usd", 0.0),
    }


# --- Chat (streaming) -------------------------------------------------------
@router.post("/stream")
async def chat_stream(req: ChatReq, request: Request, claims: dict = Depends(current_user)):
    user, allow_premium = _prepare(claims, request, req.premium)

    verdict = moderation.screen_input(req.message)
    ev = safety.assess(req.message, None if verdict.allowed else verdict.category)
    if safety.is_monitored(user) and ev.loggable:
        db.insert_safety_event(user["id"], req.session_id, ev.severity, ev.category,
                               ev.score, (not verdict.allowed) or ev.blocked,
                               safety.snippet(req.message), "; ".join(ev.reasons) or None)
    block_msg = block_model = None
    if not verdict.allowed:
        block_msg, block_model = verdict.message, "moderation"
    elif ev.blocked:
        block_msg, block_model = safety.JAILBREAK_REFUSAL, "safety"
    if block_msg:
        async def blocked_gen():
            yield _sse({"event": "delta", "text": block_msg})
            yield _sse({"event": "done", "model": block_model, "blocked": True,
                        "usage": entitlements.usage_view(user), "citations": []})
        return StreamingResponse(blocked_gen(), media_type="text/event-stream")

    session_id = req.session_id
    if not session_id:
        title = req.message[:48] + ("…" if len(req.message) > 48 else "")
        s = db.create_session(user["id"], title, req.persona)
        session_id = s["id"]
        if req.project_id:
            db.update_session(session_id, user["id"], {"project_id": req.project_id})
        req.session_id = session_id

    # --- Instant canned reply for greetings / identity small-talk (no LLM) ---
    canned = None if req.images else smalltalk.match(req.message)
    if canned:
        async def canned_gen():
            yield _sse({"event": "session", "session_id": session_id})
            yield _sse({"event": "delta", "text": canned})
            db.add_message(session_id, user["id"], "user", req.message)
            db.add_message(session_id, user["id"], "assistant", canned,
                           model="kgpt-smalltalk", tokens=0)
            db.touch_session(session_id)
            yield _sse({"event": "done", "model": "kgpt-smalltalk",
                        "usage": entitlements.usage_view(user)})
        return StreamingResponse(canned_gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache, no-transform",
                                          "Connection": "keep-alive",
                                          "X-Accel-Buffering": "no"})

    msgs, citations, meta = await _build_messages(user, req)
    classification = meta["classification"]
    chosen = _chosen_model(user, req)
    # Routed through a dedicated chain (Qwen3.5-9B first, free Groq/Zenmux
    # models as graceful fallback if it errors) rather than a hard single-model
    # override — used ONLY when the message needs language support the free
    # models lack (see _needs_multilingual_fallback), never as a default, and
    # never for explicit picks or vision (own chain).
    force_multilingual = (not chosen and not req.images
                          and _needs_multilingual_fallback(req.message))
    if chosen:
        mode, intent_str = "custom", "custom"
    else:
        if force_multilingual:
            mode, intent_str = "multilingual", "multilingual"
        elif bool(req.images):
            mode, intent_str = "vision", "vision"
        elif entitlements.should_downshift(user):
            mode, intent_str = "general", "instant"
        elif allow_premium:
            mode, intent_str = "premium", "premium"
        elif req.category and req.category in _PICKABLE:
            mode, intent_str = req.category, req.category
        else:
            mode, intent_str = classification.mode, classification.intent
    is_admin = user.get("role") == "admin"
    
    # --- Exact Match Redis Cache (0 tokens, 1ms) ---
    eligible = _cache_eligible(user, req, meta["had_context"])
    ttl = _MODE_TTLS.get(mode, 0)
    
    if eligible and ttl > 0:
        cache_key = _exact_cache_key(req.message, mode)
        hit = redis_client.cache_get_json("exact", cache_key)
        if hit and hit.get("response"):
            cached_text = hit["response"]
            cached_model = hit.get("model", "exact_cache")
            async def exact_cached_gen():
                yield _sse({"event": "session", "session_id": session_id})
                yield _sse({"event": "delta", "text": cached_text})
                db.add_message(session_id, user["id"], "user", req.message)
                db.add_message(session_id, user["id"], "assistant", cached_text,
                               model=cached_model, tokens=0)
                db.touch_session(session_id)
                auto_memory.schedule(user["id"], req.message, user.get("memory_enabled", True))
                yield _sse({"event": "done", "model": cached_model,
                            "usage": entitlements.usage_view(user), "cached": True})
            return StreamingResponse(exact_cached_gen(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache, no-transform",
                                              "Connection": "keep-alive",
                                              "X-Accel-Buffering": "no"})

    # --- Semantic cache hit: stream the cached answer, skip the LLM entirely ---
    # Gated on ttl (see non-streaming endpoint above) so personal-topic
    # messages never replay a stale cached answer.
    if eligible and ttl > 0 and meta["vec"] is not None:
        hit = rag.cache_lookup(meta["vec"])
        if hit and hit.get("response"):
            cached_text = hit["response"]
            cached_model = hit.get("model", "cache")

            async def cached_gen():
                yield _sse({"event": "session", "session_id": session_id})
                yield _sse({"event": "delta", "text": cached_text})
                db.add_message(session_id, user["id"], "user", req.message)
                db.add_message(session_id, user["id"], "assistant", cached_text,
                               model=cached_model, tokens=0)
                db.touch_session(session_id)
                auto_memory.schedule(user["id"], req.message, user.get("memory_enabled", True))
                yield _sse({"event": "done", "model": cached_model,
                            "usage": entitlements.usage_view(user), "cached": True})

            return StreamingResponse(cached_gen(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache, no-transform",
                                              "Connection": "keep-alive",
                                              "X-Accel-Buffering": "no"})

    # Hold back this many chars before streaming so a leaking canary is detected
    # and suppressed BEFORE it can reach the client.
    guard_tail = 40

    p_tok = sum(len(m.get("content", "")) if isinstance(m.get("content", ""), str) else sum(len(part.get("text", "")) for part in m.get("content", []) if isinstance(part, dict)) for m in msgs) // 4
    caps = {}
    if req.attached_source or p_tok > 15000:
        caps["long_context"] = True
    if req.images:
        caps["vision"] = True

    async def gen():
        yield _sse({"event": "session", "session_id": session_id})
        if citations:
            yield _sse({"event": "citations", "citations": citations})
        final = None
        full = ""        # everything received from the model so far
        emitted = 0      # chars already streamed to the client
        leaked = False
        try:
            with fairuse.concurrency(user["id"], is_admin):
                async for chunk in smart_router.stream(msgs, mode=mode, intent=intent_str, capabilities_required=caps, temperature=0.7, model=chosen):
                    if "delta" in chunk:
                        full += chunk["delta"]
                        if prompt_guard.output_leaked(full)[0]:
                            leaked = True
                            break
                        safe = len(full) - guard_tail
                        if safe > emitted:
                            yield _sse({"event": "delta", "text": full[emitted:safe]})
                            emitted = safe
                    elif "reasoning" in chunk:
                        yield _sse({"event": "reasoning", "text": chunk["reasoning"]})
                    elif "done" in chunk:
                        final = chunk["done"]
        except Exception as e:
            err_text = f"\n\n⚠️ Error: {str(e)}"
            yield _sse({"event": "delta", "text": err_text})
            final = {"model": "error", "completion_tokens": 0, "prompt_tokens": 0, "cost_usd": 0.0}
            full += err_text  # store the error in db so it doesn't fail empty constraint

        # Flush the held-back tail, or redact if the reply leaked.
        if leaked or prompt_guard.output_leaked(full)[0]:
            yield _sse({"event": "delta",
                        "text": ("\n\n" if emitted else "") + prompt_guard.OUTPUT_REDACTION})
            if safety.is_monitored(user):
                db.insert_safety_event(user["id"], session_id, "high", "prompt_leak", 90,
                                       True, safety.snippet(req.message), "output leak blocked")
            text_to_store = (full[:emitted] + "\n\n" + prompt_guard.OUTPUT_REDACTION) if emitted else prompt_guard.OUTPUT_REDACTION
        else:
            if len(full) > emitted:
                yield _sse({"event": "delta", "text": full[emitted:]})
            elif not full:
                msg = "\n\n*(The model returned an empty response. If you attached a document, the provider's safety filters may have blocked it.)*"
                yield _sse({"event": "delta", "text": msg})
                full += msg
            text_to_store = full

        if final or full:
            db.add_message(session_id, user["id"], "user", req.message)
            db.add_message(session_id, user["id"], "assistant", text_to_store,
                           model=(final or {}).get("model", "guard"),
                           tokens=(final or {}).get("completion_tokens", 0),
                           prompt_tokens=(final or {}).get("prompt_tokens", 0),
                           cost_usd=(final or {}).get("cost_usd", 0.0))
            db.touch_session(session_id)
            if final:
                entitlements.record_usage(user["id"], final["model"],
                                          final["prompt_tokens"], final["completion_tokens"],
                                          final["cost_usd"])
            auto_memory.schedule(user["id"], req.message, user.get("memory_enabled", True))
            _queue_memory(user, req.message, session_id)
            # Cache generic, non-personalised, non-redacted answers for reuse.
            if (eligible and final and not leaked and text_to_store 
                    and prompt_guard.OUTPUT_REDACTION not in text_to_store):
                if ttl > 0:
                    redis_client.cache_set_json("exact", _exact_cache_key(req.message, mode), 
                                                {"response": text_to_store, "model": final["model"]}, ttl)
                if ttl > 0 and meta["vec"] is not None:
                    rag.cache_store(meta["vec"], text_to_store, final["model"], question=req.message)
            usage = entitlements.usage_view(db.get_user(user["id"]))
            yield _sse({
                "event": "done",
                "model": (final or {}).get("model", "guard"),
                "usage": usage,
                "prompt_tokens": (final or {}).get("prompt_tokens", 0),
                "completion_tokens": (final or {}).get("completion_tokens", 0),
                "cost_usd": (final or {}).get("cost_usd", 0.0)
            })

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"
