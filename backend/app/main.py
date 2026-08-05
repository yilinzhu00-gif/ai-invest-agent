from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.api.router import build_api_router
from backend.app.core.config import Settings
from backend.app.core.errors import (
    CorrelatedCORSMiddleware,
    CorrelationIdMiddleware,
    http_exception_handler,
    request_validation_exception_handler,
    unexpected_exception_handler,
)
from backend.app.db.session import dispose_database_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated FastAPI application for runtime and tests."""
    current_settings = settings or Settings()
    app = FastAPI(title=current_settings.app_name, version=current_settings.app_version)
    app.state.settings = current_settings
    app.state.db_engine = None
    app.state.db_session_factory = None
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CorrelatedCORSMiddleware,
        allow_origins=current_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Correlation-ID"],
    )
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)
    app.include_router(build_api_router(current_settings), prefix=current_settings.api_v1_prefix)

    async def close_database_engine() -> None:
        await dispose_database_engine(app)

    app.router.add_event_handler("shutdown", close_database_engine)
    return app


app = create_app()
