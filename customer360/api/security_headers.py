from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Generated before the handler runs so routes (e.g. /redoc) can embed
        # the same value in the response body (e.g. the query string of a
        # bootstrap <script src>) to authorize styles it creates at runtime.
        request.state.csp_nonce = secrets.token_urlsafe(16)

        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
             "camera=(), microphone=(), geolocation=()"
)
        response.headers["Content-Security-Policy"] = (
             "default-src 'self'; "
             "script-src 'self'; "
             f"style-src 'self' 'nonce-{request.state.csp_nonce}'; "
            "connect-src 'self' https://api.github.com; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self'"
)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        return response
