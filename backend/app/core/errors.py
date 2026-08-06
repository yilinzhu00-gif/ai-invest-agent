import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


def get_correlation_id(request: Request) -> str:
    correlation_id = getattr(request.state, "correlation_id", None)
    if isinstance(correlation_id, str) and correlation_id:
        return correlation_id
    return str(uuid4())


def error_response(status_code: int, code: str, correlation_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code}, "correlation_id": correlation_id},
    )


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        provided_id = request.headers.get("X-Correlation-ID", "").strip()
        correlation_id = provided_id or str(uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class CorrelatedCORSMiddleware(CORSMiddleware):
    """Return the API error envelope when CORS rejects a preflight request."""

    def preflight_response(self, request_headers: Headers) -> Response:
        response = super().preflight_response(request_headers)
        if response.status_code < 400:
            return response

        correlation_id = request_headers.get("X-Correlation-ID", "").strip() or str(uuid4())
        response = error_response(400, "cors_preflight_rejected", correlation_id)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class RequestBodyLimitMiddleware:
    """Reject declared and streamed HTTP bodies before request parsing."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass

        body_parts: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                await self.app(scope, receive, send)
                return
            body = message.get("body", b"")
            total += len(body)
            if total > self.max_body_bytes:
                await self._reject(scope, receive, send)
                return
            body_parts.append(body)
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_body() -> Message:
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": b"".join(body_parts), "more_body": False}

        await self.app(scope, replay_body, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        state = scope.setdefault("state", {})
        correlation_id = state.get("correlation_id")
        if not isinstance(correlation_id, str) or not correlation_id:
            correlation_id = Headers(scope=scope).get("X-Correlation-ID", "").strip() or str(
                uuid4()
            )
        response = error_response(413, "request_body_too_large", correlation_id)
        response.headers["X-Correlation-ID"] = correlation_id
        await response(scope, receive, send)


async def request_validation_exception_handler(
    request: Request, _: Exception
) -> JSONResponse:
    correlation_id = get_correlation_id(request)
    logger.info("Request validation failed correlation_id=%s", correlation_id)
    return error_response(422, "validation_error", correlation_id)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = get_correlation_id(request)
    status_code = getattr(exc, "status_code", 404)
    logger.info("HTTP error status=%s correlation_id=%s", status_code, correlation_id)
    return error_response(status_code, "http_error", correlation_id)


async def unexpected_exception_handler(request: Request, _: Exception) -> JSONResponse:
    correlation_id = get_correlation_id(request)
    logger.error("Unhandled API error correlation_id=%s", correlation_id)
    return error_response(500, "internal_server_error", correlation_id)
