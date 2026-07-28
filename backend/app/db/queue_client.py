"""RabbitMQ message queue client — async task orchestration.

Follows the same pattern as supabase_client.py: module-level singleton,
thin wrappers. The worker process (app.worker) consumes from these queues.

WHY RabbitMQ:
  1. Document pipeline — upload → extract → chunk → embed → store is currently
     synchronous (blocks the HTTP request for seconds). RabbitMQ decouples each
     stage into a queue so the API returns immediately.
  2. Memory aging — nightly memory scoring/compression is a batch job that
     shouldn't run on the API server. A worker consumes from the aging queue.
  3. Durability — current auto_memory.py fires asyncio.Tasks that are lost on
     process restart. RabbitMQ persists messages to disk.
  4. Backpressure — if embedding is slow, messages queue up instead of OOMing
     the API process.
  5. Dead-letter — failed messages retry 3x, then go to a dead-letter queue
     for manual inspection instead of silently disappearing.

Queues:
  pp.documents.process   — file uploaded, needs extract → chunk → embed → store
  pp.memory.extract      — chat message needs fact extraction
  pp.memory.age          — periodic memory scoring/compression trigger
  pp.graph.update        — entity extracted, update knowledge graph
  pp.analytics.event     — usage event for analytics pipeline
"""
from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Any

from app.core.config import get_settings


@lru_cache
def _connection_params():
    """Parse RabbitMQ URL into pika connection parameters. Returns None if
    RabbitMQ is not configured."""
    settings = get_settings()
    if not settings.rabbitmq_url:
        return None
    try:
        import pika
        return pika.URLParameters(settings.rabbitmq_url)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] RabbitMQ not configured: {e}")
        return None


def _get_channel():
    """Create a new connection + channel (not pooled — pika is not thread-safe).
    For the publisher side, this is called per-publish which is fine for our
    throughput. The consumer side (worker) holds a long-lived connection."""
    params = _connection_params()
    if not params:
        return None, None
    try:
        import pika
        conn = pika.BlockingConnection(params)
        ch = conn.channel()
        return conn, ch
    except Exception as e:  # noqa: BLE001
        print(f"[warn] RabbitMQ connection failed: {e}")
        return None, None


# Queue names (constants so they're importable by the worker)
Q_DOCUMENTS_PROCESS = "pp.documents.process"
Q_MEMORY_EXTRACT = "pp.memory.extract"
Q_MEMORY_AGE = "pp.memory.age"
Q_GRAPH_UPDATE = "pp.graph.update"
Q_ANALYTICS_EVENT = "pp.analytics.event"

ALL_QUEUES = [
    Q_DOCUMENTS_PROCESS,
    Q_MEMORY_EXTRACT,
    Q_MEMORY_AGE,
    Q_GRAPH_UPDATE,
    Q_ANALYTICS_EVENT,
]


def ensure_queues() -> bool:
    """Declare all queues (idempotent). Call once at startup."""
    conn, ch = _get_channel()
    if not ch:
        return False
    try:
        import pika
        for q in ALL_QUEUES:
            ch.queue_declare(
                queue=q,
                durable=True,           # survive broker restart
                arguments={
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": f"{q}.dlq",
                },
            )
            # Dead-letter queue for failed messages
            ch.queue_declare(queue=f"{q}.dlq", durable=True)
        print("[ok] RabbitMQ queues ensured")
        return True
    except Exception as e:
        print(f"[warn] RabbitMQ queue setup failed: {e}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def publish(queue: str, message: dict[str, Any]) -> bool:
    """Publish a JSON message to a queue. Returns True on success.
    Fails silently (returns False) so publishing never breaks the API request."""
    conn, ch = _get_channel()
    if not ch:
        return False
    try:
        import pika
        ch.basic_publish(
            exchange="",
            routing_key=queue,
            body=json.dumps(message, default=str),
            properties=pika.BasicProperties(
                delivery_mode=2,        # persistent (written to disk)
                content_type="application/json",
            ),
        )
        return True
    except Exception as e:
        print(f"[warn] RabbitMQ publish to {queue} failed: {e}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


# === Convenience publishers for each queue ===================================

def publish_document_process(
    document_id: str,
    user_id: str,
    filename: str,
    s3_key: str | None = None,
) -> bool:
    """Queue a document for the extract → chunk → embed → store pipeline."""
    return publish(Q_DOCUMENTS_PROCESS, {
        "document_id": document_id,
        "user_id": user_id,
        "filename": filename,
        "s3_key": s3_key,
    })


def publish_memory_extract(user_id: str, message: str, session_id: str | None = None) -> bool:
    """Queue a chat message for automatic fact extraction."""
    return publish(Q_MEMORY_EXTRACT, {
        "user_id": user_id,
        "message": message,
        "session_id": session_id,
    })


def publish_graph_update(entity_type: str, entity_id: str, data: dict) -> bool:
    """Queue a knowledge graph update (concept mastery, relationship, etc.)."""
    return publish(Q_GRAPH_UPDATE, {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "data": data,
    })


def publish_analytics_event(event_type: str, user_id: str, data: dict) -> bool:
    """Queue an analytics event (usage, feedback, etc.)."""
    return publish(Q_ANALYTICS_EVENT, {
        "event_type": event_type,
        "user_id": user_id,
        "data": data,
    })


# === Health ==================================================================

# `available()` used to open a brand-new blocking AMQP connection (full TCP +
# auth handshake) on EVERY call, and it was being called synchronously on
# every single document upload (via upload._async_ingest_available) — meaning
# every upload, no matter how small, paid a full RabbitMQ connection-handshake
# tax, executed directly on the FastAPI event loop (blocking ALL concurrent
# requests, not just the upload) before any actual work started. A short TTL
# cache turns that into one real check per window instead of one per upload.
_AVAILABLE_CACHE_TTL = 20.0
_available_cache: tuple[float, bool] | None = None


def available() -> bool:
    """Check if RabbitMQ is reachable (cached for `_AVAILABLE_CACHE_TTL`s)."""
    global _available_cache
    now = time.monotonic()
    if _available_cache is not None and (now - _available_cache[0]) < _AVAILABLE_CACHE_TTL:
        return _available_cache[1]

    conn, ch = _get_channel()
    result = bool(ch)
    if conn:
        try:
            conn.close()
        except Exception:
            pass
    _available_cache = (now, result)
    return result


def health() -> dict:
    """Health check for /api/health."""
    conn, ch = _get_channel()
    if not ch:
        return {"status": "not_configured"}
    try:
        queue_info = {}
        for q in ALL_QUEUES:
            try:
                res = ch.queue_declare(queue=q, passive=True)
                queue_info[q] = res.method.message_count
            except Exception:
                queue_info[q] = "?"
        return {"status": "ok", "queues": queue_info}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        try:
            conn.close()
        except Exception:
            pass
