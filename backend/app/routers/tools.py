"""Tool & sandbox endpoints (P36 / P37).

Exposes:
  * ``GET  /api/tools``        — the registered function-calling tools (P37).
  * ``POST /api/tools/run``    — invoke a single deterministic tool directly.
  * ``POST /api/tools/execute``— run a Python snippet in the sandbox (P36),
    gated behind the ``code_interpreter`` feature flag.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import current_user
from app.services import fairuse, flags, sandbox, tools

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolRunReq(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


class ExecReq(BaseModel):
    code: str = Field(min_length=1, max_length=20000)
    timeout: int = Field(default=6, ge=1, le=15)


@router.get("")
async def list_tools(_: dict = Depends(current_user)):
    return {"tools": tools.SPECS, "names": tools.names()}


@router.post("/run")
async def run_tool(body: ToolRunReq, _: dict = Depends(current_user)):
    if body.name not in tools.names():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown tool: {body.name}")
    return {"name": body.name, "result": tools.run(body.name, body.args)}


@router.post("/execute")
async def execute(body: ExecReq, claims: dict = Depends(current_user)):
    if not flags.is_enabled("code_interpreter", default=True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Code interpreter is disabled.")
    # Rate-limit executions like chat to protect the host.
    fairuse.check_rate(claims["user_id"], claims.get("role") == "admin")
    return sandbox.run_python(body.code, timeout=body.timeout)
