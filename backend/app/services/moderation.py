"""Lightweight content moderation + prompt-injection screening (P39 / P43).

Design: fast, dependency-free heuristics that run inline on every message. This
is a *first line* — it blocks clearly-disallowed input with a helpful message
and flags likely prompt-injection in uploaded/untrusted content. For a stronger
guarantee a provider moderation endpoint or a small classifier model can be
slotted into `screen_input` later without changing callers.

Returns structured verdicts so the chat layer can fail soft (calm message),
never a raw stack trace.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Categories we refuse outright. Tuned to be conservative for a campus tool:
# self-harm and weapons/explosives get a caring / safety response upstream.
_SELF_HARM = re.compile(
    r"\b(kill myself|suicide|end my life|want to die|self[- ]harm|cutting myself)\b", re.I)
_WEAPONS = re.compile(
    r"\b(build a bomb|make a bomb|explosive device|nerve agent|chemical weapon|"
    r"synthesize ricin|pipe bomb)\b", re.I)
_MALWARE = re.compile(
    r"\b(write (a )?(ransomware|keylogger|computer virus|malware|trojan)|"
    r"ddos attack script|sql injection payload to hack)\b", re.I)

# Prompt-injection markers commonly embedded in untrusted documents/web text.
_INJECTION = re.compile(
    r"(ignore (all |the )?(previous|above) instructions|"
    r"disregard (your|the) (system )?prompt|"
    r"you are now (a |an )?|reveal (your |the )?system prompt|"
    r"forget (everything|your instructions)|act as (a |an )?(dan|jailbroken))", re.I)


@dataclass
class Verdict:
    allowed: bool
    category: str | None = None
    message: str | None = None


def screen_input(text: str) -> Verdict:
    """Screen a user message before it reaches the model."""
    if _SELF_HARM.search(text):
        return Verdict(
            False, "self_harm",
            "It sounds like you may be going through something really hard. You "
            "deserve support from a real person — please consider reaching out to "
            "someone you trust or a counsellor. In India you can call "
            "Tele-MANAS at 14416. I'm here to help with your studies whenever "
            "you're ready.",
        )
    if _WEAPONS.search(text):
        return Verdict(
            False, "weapons",
            "I can't help with creating weapons or dangerous materials. If this is "
            "for a chemistry or physics topic, ask me about the concept and I'll "
            "gladly explain the theory.",
        )
    if _MALWARE.search(text):
        return Verdict(
            False, "malware",
            "I can't help build malware or attack tools. I'm happy to teach "
            "security concepts, safe coding, or how to defend systems instead.",
        )
    return Verdict(True)


def screen_output(text: str) -> Verdict:
    """Post-generation guard: catch system-prompt/canary leaks and explicit
    jailbreak-success markers in the model's reply before it reaches the user."""
    from app.services import prompt_guard  # local import avoids any import cycle
    leaked, _reason = prompt_guard.output_leaked(text or "")
    if leaked:
        return Verdict(False, "prompt_leak", prompt_guard.OUTPUT_REDACTION)
    return Verdict(True)


def looks_like_injection(text: str) -> bool:
    """True if untrusted text appears to contain prompt-injection attempts."""
    return bool(_INJECTION.search(text or ""))


def sanitize_untrusted(text: str, max_chars: int = 6000) -> str:
    """Neutralise the most common injection vectors in document/web text.

    We don't try to be perfect — the real defense is the system-prompt guard in
    `prompting.UNTRUSTED_PREFACE` plus wrapping in <document> tags. Here we just
    strip obvious imperative-override lines and cap length.
    """
    cleaned_lines = []
    for line in (text or "").splitlines():
        if _INJECTION.search(line):
            continue  # drop the line entirely
        cleaned_lines.append(line)
    out = "\n".join(cleaned_lines).strip()
    return out[:max_chars]
