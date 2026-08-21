from fastapi import APIRouter, Request
from starlette.responses import Response

from backend.app.api.research import router as research_router
from backend.app.api.v1.agent_runs import router as agent_runs_router
from backend.app.api.v1.documents import router as documents_router
from backend.app.api.v1.evaluation import router as evaluation_router
from backend.app.api.v1.market_data import router as market_data_router
from backend.app.api.v1.market_reactions import router as market_reactions_router
from backend.app.api.v1.memory import router as memory_router
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
    router.include_router(agent_runs_router)
    router.include_router(documents_router)
    router.include_router(evaluation_router)
    router.include_router(market_reactions_router)
    router.include_router(memory_router)
    router.include_router(market_data_router)
    router.include_router(research_router)
    return router
