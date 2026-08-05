from fastapi import APIRouter

from backend.app.api.v1.scoring import router as scoring_router
from backend.app.core.config import Settings


def build_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/health/live", tags=["health"])
    def live_health() -> dict[str, str]:
        return {"status": "healthy", "version": settings.app_version}

    router.include_router(scoring_router)
    return router
