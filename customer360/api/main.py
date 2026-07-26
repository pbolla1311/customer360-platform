from datetime import datetime
from pathlib import Path as FilesystemPath
from typing import Any, cast

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from customer360.api.audit_logging import AuditLoggingMiddleware
from customer360.api.security import verify_api_key
from customer360.api.security_headers import SecurityHeadersMiddleware
from customer360.config import (
    API_TITLE,
    API_VERSION,
    CORS_ALLOWED_ORIGINS,
)
from customer360.infrastructure.models import Customer360Profile
from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import get_db_session
from customer360.logging_config import configure_logging

configure_logging()


class StatusResponse(BaseModel):
    application: str
    status: str
    version: str


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    version: str


class ErrorResponse(BaseModel):
    detail: str


class CustomerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    first_name: str
    last_name: str
    email: str
    city: str
    state: str
    transaction_count: int
    total_spend: float
    average_transaction_value: float
    created_at: datetime
    updated_at: datetime


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
)

app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description="Customer 360 profile and event-processing API.",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=[
        "Accept",
        "Content-Type",
        "X-API-Key",
        "X-Request-ID",
    ],
    expose_headers=[
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "Retry-After",
        "X-Request-ID",
    ],
    max_age=600,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuditLoggingMiddleware)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    cast(Any, _rate_limit_exceeded_handler),
)

STATIC_DIR = FilesystemPath(__file__).resolve().parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

LANDING_PAGE_HTML = (
    (STATIC_DIR / "site" / "index.html")
    .read_text()
    .replace("{{APP_TITLE}}", API_TITLE)
    .replace("{{APP_VERSION}}", API_VERSION)
)


SWAGGER_UI_HTML = f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link type="text/css" rel="stylesheet" href="/static/swagger/swagger-ui.css">
<link rel="shortcut icon" href="/static/swagger/favicon.png">
<title>{API_TITLE} - Swagger UI</title>
</head>
<body>
<div id="swagger-ui"></div>
<script src="/static/swagger/swagger-ui-bundle.js"></script>
<script src="/static/swagger/swagger-initializer.js"></script>
</body>
</html>
"""

CSP_NONCE_PATTERN = r"^[A-Za-z0-9_-]+$"


def _redoc_html(nonce: str) -> str:
    return f"""\
<!DOCTYPE html>
<html>
<head>
<title>{API_TITLE} - ReDoc</title>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="shortcut icon" href="/static/swagger/favicon.png">
<link rel="stylesheet" href="/static/redoc/redoc.css">
</head>
<body>
<div id="redoc-container"></div>
<script src="/redoc/pre-init.js?nonce={nonce}"></script>
<script src="/static/redoc/redoc.standalone.js"></script>
<script src="/redoc/init.js?nonce={nonce}"></script>
</body>
</html>
"""


def _style_nonce_patch_js(nonce: str) -> str:
    # ReDoc (via styled-components) and its perfect-scrollbar dependency
    # both create <style> elements at runtime with document.createElement,
    # some as soon as redoc.standalone.js is first parsed. Chrome only
    # honors a nonce set through an element's `.nonce` IDL property for
    # such dynamically-created elements -- it deliberately ignores
    # setAttribute('nonce', ...), which is what those bundles use
    # internally. Patching createElement here, before redoc.standalone.js
    # even loads, stamps the correct property on every <style> tag the
    # instant it's made, so our nonce-based style-src is honored without
    # 'unsafe-inline'.
    return (
        "(function () {\n"
        f"  var nonce = {nonce!r};\n"
        "  var nativeCreateElement = document.createElement.bind(document);\n"
        "  document.createElement = function (tagName) {\n"
        "    var element = nativeCreateElement.apply(\n"
        "      document, arguments,\n"
        "    );\n"
        "    if (\n"
        "      typeof tagName === 'string' &&\n"
        "      tagName.toLowerCase() === 'style'\n"
        "    ) {\n"
        "      element.nonce = nonce;\n"
        "    }\n"
        "    return element;\n"
        "  };\n"
        "})();\n"
    )


@app.get("/docs", include_in_schema=False)
def swagger_ui_html() -> HTMLResponse:
    return HTMLResponse(SWAGGER_UI_HTML)


@app.get("/redoc", include_in_schema=False)
def redoc_html(request: Request) -> HTMLResponse:
    nonce = cast(str, request.state.csp_nonce)
    return HTMLResponse(_redoc_html(nonce))


@app.get("/redoc/pre-init.js", include_in_schema=False)
def redoc_pre_init_js(
    nonce: str = Query(..., pattern=CSP_NONCE_PATTERN),
) -> Response:
    return Response(
        content=_style_nonce_patch_js(nonce),
        media_type="application/javascript",
    )


@app.get("/redoc/init.js", include_in_schema=False)
def redoc_init_js(
    nonce: str = Query(..., pattern=CSP_NONCE_PATTERN),
) -> Response:
    # This script is loaded as an external file (matched by script-src
    # 'self') so the Redoc.init bootstrap call never needs to be an
    # inline <script>. Passing `nonce` through Redoc.init's own options
    # covers the <style> tags it creates after this point (belt-and-
    # braces alongside the createElement patch in pre-init.js).
    #
    # hideFab/disableSearch turn off ReDoc's branding badge (which pulls
    # an image from cdn.redoc.ly) and its worker-based search index
    # (loaded from a blob: URL) rather than loosening the CSP with
    # img-src/worker-src exceptions for them.
    body = (
        f"Redoc.init({app.openapi_url!r}, "
        f"{{nonce: {nonce!r}, hideFab: true, disableSearch: true}}, "
        'document.getElementById("redoc-container"));'
    )
    return Response(content=body, media_type="application/javascript")


v1 = APIRouter(prefix="/api/v1", tags=["v1"])


def serialize_profile(profile: Customer360Profile) -> dict[str, Any]:
    return {
        "customer_id": profile.customer_id,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "email": profile.email,
        "city": profile.city,
        "state": profile.state,
        "transaction_count": profile.transaction_count,
        "total_spend": profile.total_spend,
        "average_transaction_value": profile.average_transaction_value,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


@app.get("/", include_in_schema=False)
def landing_page() -> HTMLResponse:
    return HTMLResponse(LANDING_PAGE_HTML)


@app.get(
    "/status",
    response_model=StatusResponse,
    summary="Application status",
)
def application_status() -> StatusResponse:
    return StatusResponse(
        application="Customer360 Platform",
        status="running",
        version=API_VERSION,
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
)
@v1.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
)
def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        version=API_VERSION,
    )


@app.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database unavailable",
        }
    },
    summary="Readiness check",
)
@v1.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Database unavailable",
        }
    },
    summary="Readiness check",
)
def readiness(
    session: Session = Depends(get_db_session),
) -> ReadinessResponse:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc

    return ReadinessResponse(
        status="ready",
        database="connected",
        version=API_VERSION,
    )


@app.get(
    "/customers",
    response_model=list[CustomerProfileResponse],
    summary="List customer profiles",
    dependencies=[Depends(verify_api_key)],
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded",
        }
    },
)
@v1.get(
    "/customers",
    response_model=list[CustomerProfileResponse],
    summary="List customer profiles",
    dependencies=[Depends(verify_api_key)],
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded",
        }
    },
)
@limiter.limit("60/minute")
def get_customers(
    request: Request,
    session: Session = Depends(get_db_session),
) -> list[dict[str, Any]]:
    repository = Customer360Repository(session)
    profiles = repository.list_all()
    return [serialize_profile(profile) for profile in profiles]


@app.get(
    "/customers/{customer_id}",
    response_model=CustomerProfileResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Customer not found",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ErrorResponse,
            "description": "Invalid customer ID",
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded",
        },
    },
    summary="Get customer profile",
    dependencies=[Depends(verify_api_key)],
)
@v1.get(
    "/customers/{customer_id}",
    response_model=CustomerProfileResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Customer not found",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ErrorResponse,
            "description": "Invalid customer ID",
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded",
        },
    },
    summary="Get customer profile",
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("120/minute")
def get_customer(
    request: Request,
    customer_id: str = Path(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    repository = Customer360Repository(session)
    profile = repository.get_by_customer_id(customer_id)

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return serialize_profile(profile)


app.include_router(v1)