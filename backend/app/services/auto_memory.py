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

# Only bother the extractor when the message plausibly states something personal.
_FACT_CUES = (
    "my ", "i am ", "i'm ", "im ", "i like", "i love", "i hate", "i prefer",
    "favorite", "favourite", "i work", "i'm working", "i live", "call me",
    "my name is", "remember that", "remember i", "i study", "i play", "i enjoy",
    "i want to", "my goal", "i use", "i have a", "i'm from", "i am from",
    "i'm a ", "i am a ", "you can call me",
)

_SYS = (
    "Extract durable, long-term facts about the USER from their message. "
    'Return STRICT JSON: {"facts":["short fact", ...]}. '
    "Only stable, personal facts worth remembering for months — name, preferences "
    "(favourite food/movie/music), hobbies, goals, ongoing projects, location, what "
    "they study or do. Write each as a concise third-person statement, e.g. "
    '"Favourite food is biryani" or "Is working on a robotics project". '
    "Do NOT include transient task details, questions, or anything not about the user. "
    'If there is nothing durable, return {"facts":[]}.'
)


def _looks_personal(text: str) -> bool:
    t = " " + text.lower() + " "
    return any(c in t for c in _FACT_CUES)


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
            category="instant", max_tokens=256)
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
