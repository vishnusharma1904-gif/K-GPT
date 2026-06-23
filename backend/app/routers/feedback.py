"""Pilot feedback & NPS (P50).

Students submit NPS (0-10), CSAT (1-5), or free-text feedback. Admins read an
aggregated NPS report (promoters/passives/detractors + score) for the pilot.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import current_user, require_admin
from app.db import supabase_client as db

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackReq(BaseModel):
    kind: str = Field(default="nps", pattern="^(nps|csat|free)$")
    score: int | None = Field(default=None, ge=0, le=10)
    comment: str | None = Field(default=None, max_length=2000)
    context: str | None = Field(default=None, max_length=120)


@router.post("")
async def submit(body: FeedbackReq, claims: dict = Depends(current_user)):
    db.create_feedback(claims["user_id"], body.kind, body.score,
                       body.comment, body.context)
    return {"ok": True}


@router.get("/nps")
async def nps_report(_: dict = Depends(require_admin)):
    """NPS = %promoters − %detractors (promoters 9-10, detractors 0-6)."""
    rows = db.list_feedback(kind="nps")
    scored = [r for r in rows if r.get("score") is not None]
    n = len(scored)
    if n == 0:
        return {"responses": 0, "nps": None, "promoters": 0, "passives": 0,
                "detractors": 0}
    promoters = sum(1 for r in scored if r["score"] >= 9)
    detractors = sum(1 for r in scored if r["score"] <= 6)
    passives = n - promoters - detractors
    nps = round((promoters - detractors) / n * 100)
    return {"responses": n, "nps": nps, "promoters": promoters,
            "passives": passives, "detractors": detractors,
            "avg_score": round(sum(r["score"] for r in scored) / n, 2)}


@router.get("/list")
async def list_all(kind: str | None = None, _: dict = Depends(require_admin)):
    return db.list_feedback(kind=kind, limit=2000)
