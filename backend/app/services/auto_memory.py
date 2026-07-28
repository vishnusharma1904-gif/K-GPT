"""Automatic long-term memory (P31).

Captures durable, personal facts the user shares in chat (name, favourite food /
movie, hobbies, goals, what they're working on …), embeds them into the user's
own pgvector memory, and exposes a compact "profile" the chat layer injects every
turn. Because memory rows are keyed by user_id (not session_id), what's learned in
one chat is available in every future chat — it's inter-session by design.

Extraction runs in the background (fire-and-forget) on the cheap 8B model and only
when the message looks personal, so it adds no latency or meaningful cost.
"""
from __future__ import annotations

import asyncio
import json
import re

from app.db import supabase_client as db
from app.services import embeddings, smart_router

_TASKS: set = set()  # keep refs so background tasks aren't GC'd

# Aggressively trigger the extractor on ANY first-person pronoun so we don't miss any context.
_FACT_CUES = (
    " i ", " my ", " me ", " mine ", " i'm ", " im ", " i've ", " ive ", " i'll ", " ill ", " i'd ", " id ",
    "i ", "my ", "me " # Start of string matches
)

_SYS = (
    "Extract EVERY piece of context, information, or state the USER provides about themselves. "
    'Return STRICT JSON: {"facts":["short fact", ...]}. '
    "You must aggressively capture ANY personal details: physical attributes (weight, height, age), "
    "medical conditions/history, dietary preferences, lifestyle, hobbies, goals, ongoing projects, location, "
    "what they study/do, or their current situation. "
    "Write each as a concise third-person statement, e.g. "
    '"Weighs 120kg", "Is working on a robotics project", or "Has a history of CRPS". '
    "Extract as much detail as possible so you can proactively use it in future conversations. "
    "Do NOT include the actual questions they are asking you to solve. "
    'If there is absolutely no personal context, return {"facts":[]}.'
)


def _looks_personal(text: str) -> bool:
    t = " " + text.lower() + " "
    return any(c in t for c in _FACT_CUES)


def looks_personal(text: str) -> bool:
    """Public wrapper — whether `text` references the user themselves (first
    person pronouns). Used by chat.py to keep self-referential questions
    ("what's my name", "who am I") out of the shared semantic cache, since
    their correct answer depends on the user's current memory/profile facts
    and would otherwise go stale or leak across users."""
    return _looks_personal(text)


def parse_facts(text: str) -> list[str]:
    try:
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0)) if m else {}
        facts = data.get("facts") or []
        out, seen = [], set()
        for f in facts:
            f = str(f).strip()[:200]
            key = f.lower()
            if f and key not in seen:
                seen.add(key)
                out.append(f)
        return out[:6]
    except Exception:
        return []


async def extract_and_store(user_id: str, message: str) -> list[str]:
    """Pull durable facts from one message and store them in the user's memory."""
    if not _looks_personal(message):
        return []
    try:
        res = await smart_router.complete(
            [{"role": "system", "content": _SYS},
             {"role": "user", "content": message[:2000]}],
            mode="background", intent="background", max_tokens=256)
        facts = parse_facts(res.get("text", ""))
    except Exception:
        return []
    stored = []
    for f in facts:
        try:
            db.insert_memory_scoped(user_id, f, embeddings.embed(f),
                                    kind="fact", source="auto")
            stored.append(f)
        except Exception:
            continue
    return stored


def schedule(user_id: str, message: str, memory_enabled: bool = True) -> None:
    """Fire-and-forget background extraction — never blocks the chat reply."""
    if not memory_enabled or not message:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no event loop (sync context / tests) — skip silently
    t = loop.create_task(extract_and_store(user_id, message))
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)


def profile_block(user_id: str, limit: int = 12) -> str | None:
    """Compact always-on summary of what we know about the user (facts + notes)."""
    try:
        mem = db.list_memory(user_id)
    except Exception:
        return None
    facts = [m["content"] for m in mem
             if m.get("kind") in ("fact", "note") and m.get("content")][:limit]
    if not facts:
        return None
    return "\n".join(f"- {c}" for c in facts)
