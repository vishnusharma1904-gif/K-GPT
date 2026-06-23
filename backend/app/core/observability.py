"""Observability (P5) — structured JSON logging + request-id tracing.

Lightweight and dependency-free (Sentry is optional). Every request gets an
x-request-id (echoed in the response header) and one structured log line with
method, path, status, and latency so p50/p95 can be derived from logs.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("kgpt")


def setup_logging(debug: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        t0 = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["x-request-id"] = rid
            return response
        finally:
            logger.info(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "rid": rid,
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "ms": round((time.time() - t0) * 1000, 1),
            }))


def init_sentry(dsn: str, env: str) -> bool:
    if not dsn:
        return False
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, environment=env, traces_sample_rate=0.1)
        return True
    except Exception:  # noqa: BLE001
        return False
