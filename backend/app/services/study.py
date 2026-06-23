"""Study-aid generation (P38).

Turns a chat or a piece of text into flashcards, a quiz, or a summary using the
existing SmartRouter (cheap-first). Output is coerced into structured JSON so the
frontend can render cards/questions and the result can be saved to ``study_aids``.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.services import smart_router

_KINDS = ("flashcards", "quiz", "summary")

_INSTRUCTIONS = {
    "flashcards": (
        "Create concise study flashcards from the material. Return STRICT JSON: "
        '{"cards":[{"front":"question/term","back":"answer/definition"}]} '
        "with 5-12 cards. No prose outside the JSON."
    ),
    "quiz": (
        "Create a multiple-choice quiz from the material. Return STRICT JSON: "
        '{"questions":[{"q":"...","options":["A","B","C","D"],"answer":0,'
        '"explanation":"..."}]} with 5 questions. answer is the 0-based index. '
        "No prose outside the JSON."
    ),
    "summary": (
        "Summarize the material for revision. Return STRICT JSON: "
        '{"summary":"2-3 sentence overview","points":["key point", ...]} '
        "with 5-8 points. No prose outside the JSON."
    ),
}


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort JSON recovery from a model reply."""
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def _fallback(kind: str, text: str) -> dict[str, Any]:
    snippet = text.strip()[:280]
    if kind == "summary":
        return {"summary": snippet, "points": [snippet]}
    if kind == "flashcards":
        return {"cards": [{"front": "Review", "back": snippet}]}
    return {"questions": []}


async def generate(kind: str, material: str, *, allow_premium: bool = False) -> dict[str, Any]:
    """Generate a structured study aid. ``kind`` ∈ flashcards|quiz|summary."""
    if kind not in _KINDS:
        kind = "summary"
    material = material.strip()[:12_000]
    if not material:
        return {"kind": kind, "payload": _fallback(kind, ""), "model": None}

    messages = [
        {"role": "system", "content":
            "You are a study-aid generator for college students. " + _INSTRUCTIONS[kind]},
        {"role": "user", "content": f"Material:\n\n{material}"},
    ]
    try:
        result = await smart_router.complete(
            messages, category="reasoning", allow_premium=allow_premium, max_tokens=1200)
        payload = _extract_json(result["text"]) or _fallback(kind, material)
        return {"kind": kind, "payload": payload, "model": result["model"],
                "prompt_tokens": result["prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "cost_usd": result["cost_usd"]}
    except Exception:
        return {"kind": kind, "payload": _fallback(kind, material), "model": None,
                "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
