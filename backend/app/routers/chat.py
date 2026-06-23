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

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.security import current_user
from app.db import supabase_client as db
from app.schemas import ChatReq, FeedbackReq, NewSessionReq, SessionPatch
from app.services import quota_policy as qp
from app.services import (auto_memory, embeddings, entitlements, fairuse, intent,
                          moderation, prompt_guard, prompting, safety, smart_router,
                          websearch)

settings = get_settings()
router = APIRouter(prefix="/api/chat", tags=["chat"])
HISTORY_TURNS = 10


def _load_user(claims: dict) -> dict:
    u = db.get_user(claims["user_id"])
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return u


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


def _prepare(claims: dict, request: Request, premium: bool):
    """Shared pre-flight for both chat endpoints. Returns (user, allow_premium)."""
    user = _load_user(claims)
    is_admin = user.get("role") == "admin"
    fairuse.check_rate(user["id"], is_admin)
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
             "long_context", "rag", "premium"}


def _can_pick_model(user: dict) -> bool:
    """Model picking is reserved for power hitters (Heavy tier) and admins."""
    return user.get("role") == "admin" or user.get("tier") == "heavy"


def _chosen_model(user: dict, req: ChatReq) -> str | None:
    if req.model and _can_pick_model(user):
        valid = {m["id"] for m in smart_router.selectable_models()}
        if req.model in valid:
            return req.model
    return None


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
    return intent.classify(message)


async def _build_messages(user: dict, req: ChatReq) -> tuple[list[dict], list[dict]]:
    """Assemble model messages + the citation list surfaced back to the client."""
    citations: list[dict] = []
    project = None
    if req.project_id:
        project = db.get_project(req.project_id, user["id"])

    # --- memory RAG (per-user, optionally project-scoped) ---
    memory_ctx = None
    if req.use_memory and user.get("memory_enabled", True):
        try:
            hits = db.match_memory(user["id"], embeddings.embed(req.message), limit=5)
            if hits:
                lines = []
                for h in hits:
                    src = h.get("source") or "memory"
                    lines.append(f"- ({src}) {h['content']}")
                    citations.append({"type": "memory", "source": src,
                                      "id": h.get("id"), "snippet": h["content"][:160]})
                memory_ctx = "\n".join(lines)
        except Exception:
            pass

    # --- optional web search grounding (P33) ---
    web_ctx = ""
    if req.web_search:
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

    name = (user.get("full_name") or "").split(" ")[0] or None
    profile = auto_memory.profile_block(user["id"]) if user.get("memory_enabled", True) else None
    sys = prompting.build_system_prompt(
        persona=req.persona,
        student_name=name,
        response_style=user.get("response_style"),
        custom_instructions=user.get("custom_instructions"),
        exam_mode=bool(user.get("exam_mode")),
        memory_context=combined_ctx,
        has_untrusted_docs=bool(req.web_search or memory_ctx),
        user_profile=profile,
    )
    if project and project.get("instructions"):
        sys += f"\n\nProject context — {project['name']}:\n{project['instructions']}"

    msgs = [{"role": "system", "content": sys}]
    if req.session_id:
        for m in db.get_messages(req.session_id, user["id"], limit=HISTORY_TURNS * 2):
            if m["role"] in ("user", "assistant"):
                msgs.append({"role": m["role"], "content": m["content"]})
    if req.images:
        # P34 vision: OpenAI/LiteLLM multimodal content parts.
        parts: list[dict] = [{"type": "text", "text": req.message}]
        for url in req.images[:4]:
            parts.append({"type": "image_url", "image_url": {"url": url}})
        msgs.append({"role": "user", "content": parts})
    else:
        msgs.append({"role": "user", "content": req.message})
    return msgs, citations


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

    msgs, citations = await _build_messages(user, req)
    chosen = _chosen_model(user, req)
    category = "custom" if chosen else _category(user, req.message, allow_premium, req.category, bool(req.images))

    with fairuse.concurrency(user["id"], user.get("role") == "admin"):
        result = await smart_router.complete(msgs, category=category, allow_premium=allow_premium, model=chosen)

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
                   model=result["model"], tokens=result["completion_tokens"])
    db.touch_session(session_id)
    entitlements.record_usage(user["id"], result["model"],
                              result["prompt_tokens"], result["completion_tokens"],
                              result["cost_usd"])
    auto_memory.schedule(user["id"], req.message, user.get("memory_enabled", True))

    usage = entitlements.usage_view(db.get_user(user["id"]))  # percentage only
    return {
        "session_id": session_id,
        "reply": reply_text,
        "model": result["model"],
        "category": category,
        "citations": citations,
        "usage": usage,
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

    msgs, citations = await _build_messages(user, req)
    chosen = _chosen_model(user, req)
    category = "custom" if chosen else _category(user, req.message, allow_premium, req.category, bool(req.images))
    is_admin = user.get("role") == "admin"

    # Hold back this many chars before streaming so a leaking canary is detected
    # and suppressed BEFORE it can reach the client.
    guard_tail = 40

    async def gen():
        yield _sse({"event": "session", "session_id": session_id})
        if citations:
            yield _sse({"event": "citations", "citations": citations})
        final = None
        full = ""        # everything received from the model so far
        emitted = 0      # chars already streamed to the client
        leaked = False
        with fairuse.concurrency(user["id"], is_admin):
            async for chunk in smart_router.stream(msgs, category=category, allow_premium=allow_premium, model=chosen):
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
            text_to_store = full

        if final or full:
            db.add_message(session_id, user["id"], "user", req.message)
            db.add_message(session_id, user["id"], "assistant", text_to_store,
                           model=(final or {}).get("model", "guard"),
                           tokens=(final or {}).get("completion_tokens", 0))
            db.touch_session(session_id)
            if final:
                entitlements.record_usage(user["id"], final["model"],
                                          final["prompt_tokens"], final["completion_tokens"],
                                          final["cost_usd"])
            auto_memory.schedule(user["id"], req.message, user.get("memory_enabled", True))
            usage = entitlements.usage_view(db.get_user(user["id"]))
            yield _sse({"event": "done", "model": (final or {}).get("model", "guard"), "usage": usage})

    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"
