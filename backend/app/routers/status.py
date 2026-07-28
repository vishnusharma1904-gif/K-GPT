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

from app.core.config import get_settings
from app.core.security import require_admin
from app.db import redis_client
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


def _local_ocr_summary() -> dict:
    """Coarse public rollup of the rented-GPU handwriting-OCR path (see
    vision_ocr.py `_local_ocr`): whether it's enabled, and if so whether it's
    actually serving requests or silently falling back to the cloud chain. A
    dead SSH tunnel or unloaded model produces zero user-visible errors by
    design, so this — plus the [warn]/[info] log lines already in
    vision_ocr.py — is the only way to notice besides tailing server logs.

    Deliberately omits raw error text on this PUBLIC endpoint (could leak
    infra details like the GPU box's hostname/IP from an SSH error) — check
    server logs for that detail.
    """
    settings = get_settings()
    if not settings.local_ocr_enabled:
        return {"enabled": False, "status": "disabled"}

    stats = redis_client.ocr_local_stats()
    if not stats.get("available"):
        # Redis isn't configured/reachable, so usage isn't tracked — that does
        # NOT mean the local-OCR path itself is down.
        return {"enabled": True, "status": "unknown", "reason": "usage tracking unavailable (Redis)"}

    hits, misses = stats["hits_24h"], stats["misses_24h"]
    if hits == 0 and misses == 0:
        rollup = "idle"  # enabled, but no handwritten document pages processed in the last 24h
    elif hits == 0:
        rollup = "degraded"  # every attempt in the window fell back — tunnel/model likely down
    elif misses > 0:
        rollup = "degraded"  # partial failures
    else:
        rollup = "operational"

    return {
        "enabled": True,
        "status": rollup,
        "hits_24h": hits,
        "misses_24h": misses,
        "last_success_at": stats["last_success_at"],
        "last_failure_at": stats["last_failure_at"],
        "last_latency_s": stats["last_latency_s"],
    }


@router.get("")
async def public_status():
    """Public status — safe to expose; no tenant data."""
    health = smart_router.health()
    open_circuits = health.get("open_circuits", [])
    try:
        incidents = db.list_open_incidents()
    except Exception:
        incidents = []

    # Local-OCR degradation is deliberately excluded from the top-level
    # `overall` rollup below: by design a failed local attempt falls back to
    # the fully-working paid cloud chain, so it's a cost/speed regression for
    # handwritten-document pages, never a user-facing outage. It gets its own
    # field instead of paging anyone.
    local_ocr = _local_ocr_summary()

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
        "local_ocr": local_ocr,
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
