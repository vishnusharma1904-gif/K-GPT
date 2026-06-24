from fastapi import APIRouter
from app.services import smart_router
from app.db import postgres_client, redis_client, qdrant_client, queue_client, neo4j_client

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def health():
    return {
        "status": "ok",
        "router": smart_router.health(),
        "postgres": await postgres_client.health(),
        "redis": redis_client.health(),
        "qdrant": qdrant_client.health(),
        "rabbitmq": queue_client.health(),
        "neo4j": neo4j_client.health(),
    }
