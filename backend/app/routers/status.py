"""Reliability & status page (P47).

Public, unauthenticated status summary aggregating:
  * provider circuit-breaker state from the SmartRouter,
  * open incidents (admin-posted),
  * a coarse overall status (operational / degraded / outage).

Admin endpoints post and resolve incidents. Pair with an external uptime monitor
(see DEPLOYMENT.md) hitting ``/api/health`` for true uptime tracking.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import require_admin
from app.db import supabase_client as db
from app.services import smart_router

router = APIRouter(prefix="/api/status", tags=["status"])


class IncidentReq(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    severity: str = Field(default="minor", pattern="^(minor|major|critical)$")
    body: str | None = Field(default=None, max_length=4000)


class IncidentPatch(BaseModel):
    status: str = Field(pattern="^(investigating|identified|monitoring|resolved)$")
    body: str | None = Field(default=None, max_length=4000)


@router.get("")
async def public_status():
    """Public status — safe to expose; no tenant data."""
    health = smart_router.health()
    open_circuits = health.get("open_circuits", [])
    try:
        incidents = db.list_open_incidents()
    except Exception:
        incidents = []

    if any(i.get("severity") == "critical" for i in incidents):
        overall = "outage"
    elif open_circuits or incidents:
        overall = "degraded"
    else:
        overall = "operational"

    return {
        "status": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "degraded_models": open_circuits,
        "incidents": [
            {"id": i["id"], "title": i["title"], "severity": i["severity"],
             "status": i["status"], "created_at": i.get("created_at")}
            for i in incidents
        ],
    }


@router.get("/incidents")
async def incidents(_: dict = Depends(require_admin)):
    return db.list_incidents(limit=50)


@router.post("/incidents")
async def create_incident(body: IncidentReq, _: dict = Depends(require_admin)):
    return db.create_incident(body.title, body.severity, body.body)


@router.patch("/incidents/{incident_id}")
async def update_incident(incident_id: str, body: IncidentPatch,
                          _: dict = Depends(require_admin)):
    patch: dict = {"status": body.status}
    if body.body is not None:
        patch["body"] = body.body
    if body.status == "resolved":
        patch["resolved_at"] = datetime.now(timezone.utc).isoformat()
    updated = db.update_incident(incident_id, patch)
    return updated or {"ok": True}
