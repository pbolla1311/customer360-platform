import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

audit_logger = logging.getLogger("customer360.audit")


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round(
                (time.perf_counter() - started_at) * 1000,
                2,
            )

            audit_logger.exception(
                "HTTP request failed",
                extra={
                    "event_type": "http_request",
                    "request_id": request_id,
                    "http_method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "client_ip": self._get_client_ip(request),
                },
            )
            raise

        duration_ms = round(
            (time.perf_counter() - started_at) * 1000,
            2,
        )

        response.headers["X-Request-ID"] = request_id

        audit_logger.info(
            "HTTP request completed",
            extra={
                "event_type": "http_request",
                "request_id": request_id,
                "http_method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": self._get_client_ip(request),
            },
        )

        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        forwarded_for = request.headers.get("X-Forwarded-For")

        if forwarded_for:
            return forwarded_for.split(",", maxsplit=1)[0].strip()

        if request.client is not None:
            return request.client.host

        return "unknown"