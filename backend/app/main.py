"""K-GPT — multi-tenant campus AI backend (FastAPI)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.observability import (RequestContextMiddleware, init_sentry,
                                    setup_logging)
from app.routers import (account, admin, auth, billing, chat, export, feedback,
                         figures, health, memory, oauth, projects, prompts, share,
                         status, study, tools, upload, voice)
from app.db import postgres_client, qdrant_client, queue_client
from prometheus_fastapi_instrumentator import Instrumentator

settings = get_settings()
setup_logging(settings.debug)
init_sentry(settings.sentry_dsn, settings.env)

# Expose provider keys to LiteLLM via os.environ
for _name, _val in {
    "GROQ_API_KEY": settings.groq_api_key,
    "OPENAI_API_KEY": settings.openai_api_key,
    "ANTHROPIC_API_KEY": settings.anthropic_api_key,
    "GEMINI_API_KEY": settings.gemini_api_key,
    "MISTRAL_API_KEY": settings.mistral_api_key,
    "FIREWORKS_API_KEY": settings.fireworks_api_key,
    "OPENROUTER_API_KEY": settings.openrouter_api_key,
    "DEEPSEEK_API_KEY": settings.deepseek_api_key,
    "COHERE_API_KEY": settings.cohere_api_key,
    "NVIDIA_NIM_API_KEY": settings.nvidia_nim_api_key,
    "ZENMUX_API_KEY": settings.zenmux_api_key,
    "TAVILY_API_KEY": settings.tavily_api_key,
}.items():
    if _val:
        os.environ[_name] = _val


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm the embedding model so the first chat isn't slow.
    try:
        from app.services import embeddings
        embeddings.warm()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] embedding warmup skipped: {e}")

    # Initialize Prompt Pulse Phase 1 infrastructure. Each store is optional and
    # may be configured-but-unreachable (e.g. running the API without the full
    # Docker stack), so a failure here must NEVER crash startup — log and move on.
    try:
        await postgres_client.init_pool()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] postgres init skipped: {e}")
    try:
        qdrant_client.ensure_collections()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] qdrant init skipped: {e}")
    try:
        queue_client.ensure_queues()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] rabbitmq init skipped: {e}")

    # Nightly quota reset + auto-tiering + subscription expiry (Epic B/C).
    #
    # This must fire on exactly ONE process. Under `uvicorn --workers N` every
    # worker runs this lifespan, so we elect a single leader:
    #   * Redis configured  -> a distributed lock (SET NX) picks one winner and
    #     the leader refreshes it every few minutes so it can be reclaimed if the
    #     process dies. No double-fire even across many workers/replicas.
    #   * No Redis          -> fall back to the `scheduler_enabled` flag; operators
    #     running multiple workers set it false on all but one.
    from app.db import redis_client
    _LEADER_LOCK = "scheduler:leader"
    _LOCK_TTL = 900  # 15 min; refreshed every 5
    scheduler = None
    is_leader = False
    if settings.scheduler_enabled:
        if redis_client.configured():
            is_leader = redis_client.try_acquire_lock(_LEADER_LOCK, _LOCK_TTL)
        else:
            is_leader = True  # single-instance fallback (see scheduler_enabled)

    if is_leader and settings.supabase_url and settings.supabase_service_key:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger
            from app.services import entitlements, memory_compressor

            async def _nightly():
                try:
                    entitlements.run_nightly()
                except Exception as e:  # noqa: BLE001
                    print(f"[warn] nightly sweep failed: {e}")
                try:
                    from app.services import cost_governance
                    cost_governance.enforce()   # P46 budget throttle sweep
                except Exception as e:  # noqa: BLE001
                    print(f"[warn] cost-governance sweep failed: {e}")
                try:
                    await memory_compressor.run_nightly_compression()
                except Exception as e:  # noqa: BLE001
                    print(f"[warn] memory compression failed: {e}")

            scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
            scheduler.add_job(_nightly, CronTrigger(hour=0, minute=5))  # 00:05 IST
            if redis_client.configured():
                # Keep leadership alive; if this process dies the lock expires and
                # another worker can take over on its next restart.
                scheduler.add_job(
                    lambda: redis_client.refresh_lock(_LEADER_LOCK, _LOCK_TTL),
                    IntervalTrigger(seconds=_LOCK_TTL // 3),
                )
            scheduler.start()
            print("[ok] nightly entitlements sweep scheduled (00:05 IST) — this is the scheduler leader")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] scheduler not started: {e}")
    elif settings.scheduler_enabled and settings.supabase_url and settings.supabase_service_key:
        print("[ok] scheduler leadership held by another worker; not scheduling here")

    yield

    # Shutdown Prompt Pulse infrastructure
    await postgres_client.close_pool()

    if scheduler:
        scheduler.shutdown(wait=False)


# Disable the interactive API docs / OpenAPI schema in production — they expose
# the full endpoint surface to anyone. Available in dev for convenience.
_docs = ({"docs_url": None, "redoc_url": None, "openapi_url": None}
         if settings.is_prod else {})
app = FastAPI(title="K-GPT API", version="1.2.0", lifespan=lifespan, **_docs)

# Prometheus metrics. Exposed for Grafana; do NOT route /metrics publicly via
# Caddy/Cloudflare — Prometheus should scrape it over the internal Docker network.
Instrumentator().instrument(app).expose(app)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Defense-in-depth response headers (safe defaults; does not touch CORS/SSE).
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(self), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-XSS-Protection": "0",
}


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


for r in (auth.router, oauth.router, chat.router, memory.router, account.router,
          billing.router, admin.router, health.router,
          projects.router, share.router, upload.router, figures.router,
          prompts.router, study.router, tools.router, status.router,
          feedback.router, voice.router, export.router):
    app.include_router(r)


@app.get("/")
async def root():
    return {"app": "K-GPT", "status": "ok", "version": "1.2.0", "docs": "/docs"}
