from fastapi import APIRouter
from app.services import smart_router

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def health():
    return {"status": "ok", "router": smart_router.health()}
