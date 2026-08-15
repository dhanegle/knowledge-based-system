from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_configured": bool(settings.llm_api_key),
    }
