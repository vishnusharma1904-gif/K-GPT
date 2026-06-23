"""Safety monitoring + jailbreak detection (campus safeguarding).

A second, monitoring-focused layer on top of `moderation.screen_input`. Where
moderation decides the *user-facing* refusal message, this module assigns a
**severity** and **category** so the admin console can triage, and decides
whether a clearly-abusive attempt should be **blocked in real time**.

Design goals:
  * Fast, dependency-free regex heuristics (runs inline on every message).
  * Never throws — returns a structured `Assessment` the chat layer can log.
  * Conservative: only *high* severity blocks; low/medium are logged for review.

Monitoring scope: only "campus" plans (semester / monthly) are monitored. The
annual tier is treated as general public and is NOT logged for admin review
(real-time blocking of dangerous content still applies to everyone).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services import prompt_guard

# Plans whose owners are students under campus safeguarding. Annual = public.
MONITORED_PLANS = {"semester", "monthly"}

SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


def is_monitored(user: dict) -> bool:
    """True if this user's chats may be reviewed by admins for safety."""
    if not user or user.get("role") == "admin":
        return False
    return (user.get("plan") or "") in MONITORED_PLANS


# --- Detection patterns -----------------------------------------------------
# Jailbreak / role-override attempts aimed at the assistant itself.
_JAILBREAK = re.compile(
    r"(ignore (all |the )?(previous|above|prior) (instructions|prompts?)|"
    r"disregard (your|the|all) (system )?(prompt|instructions|rules)|"
    r"forget (everything|all|your) (instructions|rules|previous)|"
    r"you are now (a |an |in )?|pretend (you are|to be)|"
    r"act as (a |an )?(dan|jailbroken|unfiltered|unrestricted)|"
    r"\bdo anything now\b|\bdan mode\b|developer mode|"
    r"bypass (your |the )?(filter|safety|guard|restriction)|"
    r"without any (restrictions|filters|rules|guardrails)|"
    r"reveal (your |the )?(system )?(prompt|instructions)|"
    r"what (are|were) your (system )?(instructions|prompt)|"
    r"repeat (the words |everything )?above|print your (system )?prompt|"
    r"enable (jailbreak|dan|developer) mode)", re.I)

# Attempts to extract the system prompt / hidden config.
_PROMPT_LEAK = re.compile(
    r"(system prompt|initial instructions|your guidelines|the text above|"
    r"everything before this|your configuration|hidden (prompt|instructions))", re.I)

_SELF_HARM = re.compile(
    r"\b(kill myself|suicide|end my life|want to die|self[- ]harm|"
    r"cutting myself|harm myself|don'?t want to live)\b", re.I)

_WEAPONS = re.compile(
    r"\b(build a bomb|make a bomb|explosive device|nerve agent|chemical weapon|"
    r"synthesize ricin|pipe bomb|3d print(ed)? gun|untraceable (gun|weapon))\b", re.I)

_MALWARE = re.compile(
    r"\b(write (a )?(ransomware|keylogger|computer virus|malware|trojan|spyware)|"
    r"ddos attack script|sql injection payload to hack|steal (passwords|credentials))\b", re.I)


@dataclass
class Assessment:
    severity: str = "none"          # none | low | medium | high
    category: str = "none"          # jailbreak | prompt_leak | self_harm | weapons | malware | none
    score: int = 0                  # 0-100 rough confidence
    blocked: bool = False           # should the request be refused outright?
    reasons: list[str] = field(default_factory=list)

    @property
    def loggable(self) -> bool:
        return self.severity != "none"


def assess(text: str, moderation_category: str | None = None) -> Assessment:
    """Classify a user message. `moderation_category` is the verdict category
    from `moderation.screen_input` (so we don't re-implement those refusals)."""
    t = text or ""
    reasons: list[str] = []

    # High-severity safety categories (also blocked by moderation upstream).
    if moderation_category == "self_harm" or _SELF_HARM.search(t):
        return Assessment("high", "self_harm", 95, blocked=True,
                          reasons=["self-harm language detected"])
    if moderation_category == "weapons" or _WEAPONS.search(t):
        return Assessment("high", "weapons", 95, blocked=True,
                          reasons=["weapons/dangerous-materials request"])
    if moderation_category == "malware" or _MALWARE.search(t):
        return Assessment("high", "malware", 90, blocked=True,
                          reasons=["malware/attack-tooling request"])

    # Jailbreak / prompt-injection aimed at the assistant. Combine the legacy
    # markers with the obfuscation-resistant guard score (de-leet/de-space/base64).
    jb = bool(_JAILBREAK.search(t))
    leak = bool(_PROMPT_LEAK.search(t))
    g_score, g_reasons = prompt_guard.score_input(t)
    if jb:
        reasons.append("jailbreak / instruction-override phrasing")
    if leak:
        reasons.append("system-prompt extraction attempt")
    reasons.extend(g_reasons)

    score = max(g_score, 85 if (jb and leak) else 55 if jb else 30 if leak else 0)
    if score == 0:
        return Assessment("none", "none", 0, blocked=False, reasons=[])
    if score >= prompt_guard.BLOCK_THRESHOLD or (jb and leak):
        return Assessment("high", "jailbreak", min(score, 99), blocked=True, reasons=reasons)
    if score >= prompt_guard.SOFT_THRESHOLD:
        return Assessment("medium", "jailbreak", score, blocked=False, reasons=reasons)
    return Assessment("low", "prompt_leak" if (leak and not jb) else "jailbreak",
                      score, blocked=False, reasons=reasons)


# Friendly refusal shown when a jailbreak attempt is blocked (non-safety).
JAILBREAK_REFUSAL = (
    "I can't follow instructions that try to override my guidelines or reveal my "
    "system configuration. I'm still happy to help with your studies, coding, "
    "writing, or any genuine question — what would you like to work on?"
)


def snippet(text: str, limit: int = 280) -> str:
    s = " ".join((text or "").split())
    return s[:limit]
