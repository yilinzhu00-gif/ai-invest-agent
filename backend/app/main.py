from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from prometheus_client import make_asgi_app
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.api.router import build_api_router
from backend.app.core.config import Settings
from backend.app.core.errors import (
    CorrelatedCORSMiddleware,
    CorrelationIdMiddleware,
    RequestBodyLimitMiddleware,
    http_exception_handler,
    request_validation_exception_handler,
    unexpected_exception_handler,
)
from backend.app.db.session import dispose_database_engine
from backend.app.observability.metrics import HTTP_REQUESTS
from backend.app.security.authentication import build_oidc_jwt_validator


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated FastAPI application for runtime and tests."""
    current_settings = settings or Settings()
    app = FastAPI(title=current_settings.app_name, version=current_settings.app_version)
    app.state.settings = current_settings
    app.state.db_engine = None
    app.state.db_session_factory = None
    app.state.agent_run_executor = None
    app.state.oidc_validator = None
    if current_settings.app_env == "production":
        assert current_settings.oidc_issuer is not None
        assert current_settings.oidc_audience is not None
        assert current_settings.oidc_jwks_url is not None
        app.state.oidc_validator = build_oidc_jwt_validator(
            issuer=current_settings.oidc_issuer,
            audience=current_settings.oidc_audience,
            jwks_url=current_settings.oidc_jwks_url,
            clock_skew_seconds=current_settings.oidc_clock_skew_seconds,
            allowed_token_types=current_settings.oidc_access_token_type_list,
        )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=current_settings.max_request_body_bytes,
        document_upload_max_bytes=current_settings.document_upload_max_bytes,
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CorrelatedCORSMiddleware,
        allow_origins=current_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Content-Type",
            "Last-Event-ID",
            "X-Correlation-ID",
            "X-Development-Principal-ID",
            "X-Development-Workspace-ID",
            "X-Workspace-ID",
            "Authorization",
        ],
    )
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)
    app.include_router(build_api_router(current_settings), prefix=current_settings.api_v1_prefix)
    app.mount("/metrics", make_asgi_app())

    @app.middleware("http")
    async def record_request_metrics(request: Request, call_next: object) -> object:
        response = await call_next(request)  # type: ignore[operator]
        HTTP_REQUESTS.labels(method=request.method, status=str(response.status_code)).inc()
        return response

    async def close_database_engine() -> None:
        await dispose_database_engine(app)

    app.router.add_event_handler("shutdown", close_database_engine)
    return app


app = create_app()
