from fastapi import APIRouter, Request
from starlette.responses import Response

from backend.app.api.v1.scoring import router as scoring_router
from backend.app.core.config import Settings
from backend.app.core.errors import error_response, get_correlation_id
from backend.app.db.health import is_database_ready


def build_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/health/live", tags=["health"])
    def live_health() -> dict[str, str]:
        return {"status": "healthy", "version": settings.app_version}

    @router.get("/health/ready", tags=["health"], response_model=None)
    async def ready_health(request: Request) -> dict[str, str] | Response:
        if await is_database_ready(settings):
            return {"status": "ready", "version": settings.app_version}
        return error_response(503, "database_not_ready", get_correlation_id(request))

    router.include_router(scoring_router)
    return router
