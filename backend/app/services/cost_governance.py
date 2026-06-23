"""Cost governance (P46).

Per-cohort monthly spend budgets with alerting and automatic throttle on breach.
Pure-ish: the DB I/O is isolated in two functions so the evaluation logic is
unit-testable. Hooked into the nightly sweep and queryable from the admin console.

A throttled cohort has ``feature``-level downshift applied at request time (the
chat layer can read ``is_throttled`` to force the cheapest model category).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db import supabase_client as db


def _month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def evaluate_cohort(budget: dict, spend_usd: float) -> dict:
    """Pure policy: given a budget row + month-to-date spend, decide state."""
    cap = float(budget.get("monthly_usd") or 0)
    alert_pct = int(budget.get("alert_pct") or 80)
    pct = round(spend_usd / cap * 100, 1) if cap > 0 else 0.0
    breached = cap > 0 and spend_usd >= cap
    alerting = cap > 0 and pct >= alert_pct
    return {
        "cohort": budget["cohort"],
        "monthly_usd": cap,
        "spend_usd": round(spend_usd, 4),
        "percent": pct,
        "alerting": alerting,
        "breached": breached,
        "should_throttle": breached,
    }


def evaluate_all() -> list[dict]:
    """Evaluate every cohort budget against month-to-date spend."""
    since = _month_start_iso()
    out = []
    for b in db.list_cohort_budgets():
        spend = db.cohort_spend_since(b["cohort"], since)
        out.append(evaluate_cohort(b, spend))
    return out


def enforce() -> dict:
    """Apply / lift auto-throttle based on current spend. Safe to run nightly."""
    results = evaluate_all()
    changed = []
    for r in results:
        budget = db.get_cohort_budget(r["cohort"]) or {}
        currently = bool(budget.get("throttled"))
        if r["should_throttle"] and not currently:
            db.set_cohort_throttle(r["cohort"], True)
            changed.append({"cohort": r["cohort"], "throttled": True})
        elif not r["should_throttle"] and currently:
            db.set_cohort_throttle(r["cohort"], False)
            changed.append({"cohort": r["cohort"], "throttled": False})
    return {"evaluated": len(results), "changed": changed,
            "alerting": [r["cohort"] for r in results if r["alerting"]]}


def is_cohort_throttled(cohort: str | None) -> bool:
    if not cohort:
        return False
    b = db.get_cohort_budget(cohort)
    return bool(b and b.get("throttled"))
