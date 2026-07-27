import html
import time
from datetime import UTC, datetime
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
from customer360.api.pipeline_simulation_engine import (
    ENGINE,
    FailureType,
    PipelineEngineError,
)
from customer360.api.pipeline_telemetry import (
    HealthStatus,
    KpiMetrics,
    PipelineSummary,
    ServiceHealth,
    StageMetric,
    build_charts,
    build_customer_flow,
    build_event_stream,
    build_service_health,
    build_summary,
    compute_kpis,
    status_from_thresholds,
)
from customer360.api.security import verify_api_key
from customer360.api.security_headers import SecurityHeadersMiddleware
from customer360.config import (
    API_TITLE,
    API_VERSION,
    AUTHOR_LINKEDIN_URL,
    CORS_ALLOWED_ORIGINS,
)
from customer360.infrastructure.models import Customer360Profile
from customer360.infrastructure.repository import (
    Customer360Repository,
    RepositoryError,
)
from customer360.infrastructure.session import get_db_session
from customer360.logging_config import configure_logging
from customer360.outbox.repository import OutboxRepository

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


class DemoSummaryResponse(BaseModel):
    total_customers: int
    active_profiles: int
    total_transactions: int


class PipelineKpiResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    messages_processed: int
    successful_events: int
    failed_events: int
    retry_queue: int
    dlq_messages: int
    avg_processing_time_ms: float
    events_per_sec: float
    consumer_lag: int


class PipelineStageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    count: int
    status: str


class PipelineSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generated_at: datetime
    kpis: PipelineKpiResponse
    stages: list[PipelineStageResponse]
    simulated: bool = True


class PipelineEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    event_type: str
    status: str
    detail: str


class PipelineServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    status: str
    latency_ms: float
    last_heartbeat: datetime


class PipelineChartSeriesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    categories: list[str]
    values: list[float]


class PipelineChartsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    messages_per_minute: PipelineChartSeriesResponse
    retries_over_time: PipelineChartSeriesResponse
    dlq_trend: PipelineChartSeriesResponse
    success_series: PipelineChartSeriesResponse
    failure_series: PipelineChartSeriesResponse
    latency_ms: PipelineChartSeriesResponse
    top_event_types: PipelineChartSeriesResponse


class PipelineCustomerFlowStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    timestamp: datetime
    status: str


class TraceStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    status: str
    processing_time_ms: float
    timestamp: datetime


class SimulatedEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    event_type: str
    customer_id: str
    created_at: datetime
    status: str
    retry_count: int
    failure_type: str | None


class EventTraceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event: SimulatedEventResponse
    steps: list[TraceStepResponse]
    replay: bool


class PipelineStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current_event: SimulatedEventResponse | None
    consumer_healthy: bool
    generated_count: int
    success_count: int
    failed_count: int
    retry_queue_count: int
    dlq_count: int
    has_replayable_event: bool


class InjectFailureRequest(BaseModel):
    failure_type: FailureType


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


def _linkedin_link_html(css_class: str) -> str:
    if AUTHOR_LINKEDIN_URL:
        href = html.escape(AUTHOR_LINKEDIN_URL, quote=True)
        return (
            f'<a class="{css_class}" href="{href}" '
            'target="_blank" rel="noopener noreferrer">LinkedIn</a>'
        )

    return (
        f'<span class="{css_class} link-placeholder" aria-disabled="true" '
        'title="LinkedIn profile not yet configured">LinkedIn</span>'
    )


LANDING_PAGE_HTML = (
    (STATIC_DIR / "site" / "index.html")
    .read_text()
    .replace("{{APP_TITLE}}", API_TITLE)
    .replace("{{APP_VERSION}}", API_VERSION)
    .replace("{{LINKEDIN_LINK_AUTHOR}}", _linkedin_link_html("author-link"))
    .replace("{{LINKEDIN_LINK_FOOTER}}", _linkedin_link_html("footer-link"))
)


DEMO_PAGE_HTML = (
    (STATIC_DIR / "demo" / "index.html")
    .read_text()
    .replace("{{APP_TITLE}}", API_TITLE)
    .replace("{{APP_VERSION}}", API_VERSION)
)


PIPELINE_PAGE_HTML = (
    (STATIC_DIR / "demo" / "pipeline" / "index.html")
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


@app.get("/demo", include_in_schema=False)
def demo_dashboard() -> HTMLResponse:
    return HTMLResponse(DEMO_PAGE_HTML)


# The routes below back the /demo dashboard only. They deliberately do not
# require verify_api_key: they only ever serve seeded, fictional demo rows
# (see scripts/seed_demo_customers.py), and the real X-API-Key secret must
# never reach browser-side JS. The authenticated /customers and
# /api/v1/customers routes above are unchanged. Kept out of the OpenAPI
# schema for the same reason the HTML routes above are (docs/redoc/landing).
@app.get(
    "/demo/api/summary",
    response_model=DemoSummaryResponse,
    include_in_schema=False,
)
@limiter.limit("60/minute")
def demo_summary(
    request: Request,
    session: Session = Depends(get_db_session),
) -> DemoSummaryResponse:
    repository = Customer360Repository(session)
    profiles = repository.list_all()

    return DemoSummaryResponse(
        total_customers=len(profiles),
        active_profiles=sum(
            1 for profile in profiles if profile.transaction_count > 0
        ),
        total_transactions=sum(
            profile.transaction_count for profile in profiles
        ),
    )


@app.get(
    "/demo/api/customers",
    response_model=list[CustomerProfileResponse],
    include_in_schema=False,
)
@limiter.limit("60/minute")
def demo_customers(
    request: Request,
    session: Session = Depends(get_db_session),
) -> list[dict[str, Any]]:
    repository = Customer360Repository(session)
    profiles = repository.list_all()
    return [serialize_profile(profile) for profile in profiles]


@app.get(
    "/demo/api/customers/{customer_id}",
    response_model=CustomerProfileResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Customer not found",
        },
    },
    include_in_schema=False,
)
@limiter.limit("120/minute")
def demo_customer(
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


# ---------------------------------------------------------------------------
# /demo/pipeline -- see customer360/api/pipeline_telemetry.py for why almost
# everything below is a labeled simulation rather than live Kafka/outbox
# telemetry, and README -> Pipeline Monitor for the full writeup.
# ---------------------------------------------------------------------------

_PIPELINE_REAL_INPUTS_TTL_SECONDS = 3.0
_pipeline_real_inputs_cache: tuple[float, tuple[int, int, bool]] | None = None


def _real_pipeline_inputs(session: Session) -> tuple[int, int, bool]:
    """(real_customer_count, real_outbox_pending, db_reachable), cached briefly.

    The dashboard calls summary/events/services/charts within moments of each
    other on every load and every poll; without this cache each of those
    would repeat the same count queries against the same data.
    """

    global _pipeline_real_inputs_cache

    now_monotonic = time.monotonic()
    if (
        _pipeline_real_inputs_cache is not None
        and now_monotonic - _pipeline_real_inputs_cache[0]
        < _PIPELINE_REAL_INPUTS_TTL_SECONDS
    ):
        return _pipeline_real_inputs_cache[1]

    repository = Customer360Repository(session)

    try:
        customer_count = repository.count_all()
    except RepositoryError:
        session.rollback()
        customer_count = 0

    try:
        outbox_pending = len(OutboxRepository(session).pending())
    except SQLAlchemyError:
        session.rollback()
        outbox_pending = 0

    try:
        session.execute(text("SELECT 1"))
        db_reachable = True
    except SQLAlchemyError:
        session.rollback()
        db_reachable = False

    result = (customer_count, outbox_pending, db_reachable)
    _pipeline_real_inputs_cache = (now_monotonic, result)
    return result


@app.get("/demo/pipeline", include_in_schema=False)
def pipeline_dashboard() -> HTMLResponse:
    return HTMLResponse(PIPELINE_PAGE_HTML)


# Stages the Control Center engine can move counts through. Producer/Kafka
# Topic count every generated event; Consumer counts only ones that
# eventually succeeded; Retry Queue/DLQ mirror the engine's own buckets
# exactly (see PipelineSimulationEngine.get_state). Outbox and PostgreSQL
# are deliberately absent: Outbox already reflects real inserted rows via
# _real_pipeline_inputs, and PostgreSQL must stay strictly real.
_ENGINE_STAGE_DELTA_KEYS: dict[str, str] = {
    "Producer": "generated_count",
    "Kafka Topic": "generated_count",
    "Consumer": "success_count",
    "Retry Queue": "retry_queue_count",
    "Dead Letter Queue": "dlq_count",
}


def _apply_engine_overlay_to_summary(summary: PipelineSummary) -> PipelineSummary:
    """Additively overlays the Control Center engine's counters onto the
    ambient (time-based) summary. At the engine's initial/reset state every
    delta is 0, so this reproduces the pre-existing output exactly."""

    state = ENGINE.get_state()
    kpis = summary.kpis

    overlaid_kpis = KpiMetrics(
        messages_processed=kpis.messages_processed + state.generated_count,
        successful_events=kpis.successful_events + state.success_count,
        failed_events=kpis.failed_events + state.failed_count,
        retry_queue=kpis.retry_queue + state.retry_queue_count,
        dlq_messages=kpis.dlq_messages + state.dlq_count,
        avg_processing_time_ms=kpis.avg_processing_time_ms,
        events_per_sec=kpis.events_per_sec,
        consumer_lag=kpis.consumer_lag,
    )

    overlaid_stages = []
    for stage in summary.stages:
        delta_key = _ENGINE_STAGE_DELTA_KEYS.get(stage.name)
        if delta_key is None:
            overlaid_stages.append(stage)
            continue

        new_count = stage.count + getattr(state, delta_key)
        if stage.name == "Retry Queue":
            new_status = status_from_thresholds(new_count, warning=10, critical=20)
        elif stage.name == "Dead Letter Queue":
            new_status = status_from_thresholds(new_count, warning=3, critical=8)
        else:
            new_status = stage.status
        overlaid_stages.append(StageMetric(stage.name, new_count, new_status))

    return PipelineSummary(
        generated_at=summary.generated_at, kpis=overlaid_kpis, stages=overlaid_stages
    )


def _apply_engine_overlay_to_services(services: list[ServiceHealth]) -> list[ServiceHealth]:
    """Only ever pushes the Consumer card toward CRITICAL -- never masks a
    real ambient warning, and never touches Database/API (strictly real)."""

    if ENGINE.get_state().consumer_healthy:
        return services

    return [
        ServiceHealth(
            name=service.name,
            status=HealthStatus.CRITICAL,
            latency_ms=service.latency_ms,
            last_heartbeat=service.last_heartbeat,
        )
        if service.name == "Consumer"
        else service
        for service in services
    ]


@app.get(
    "/demo/api/pipeline/summary",
    response_model=PipelineSummaryResponse,
    include_in_schema=False,
)
@limiter.limit("60/minute")
def pipeline_summary(
    request: Request,
    session: Session = Depends(get_db_session),
) -> PipelineSummaryResponse:
    customer_count, outbox_pending, db_reachable = _real_pipeline_inputs(session)
    summary = build_summary(
        datetime.now(UTC),
        real_customer_count=customer_count,
        real_outbox_pending=outbox_pending,
        db_reachable=db_reachable,
    )
    overlaid = _apply_engine_overlay_to_summary(summary)
    return PipelineSummaryResponse.model_validate(overlaid)


@app.get(
    "/demo/api/pipeline/events",
    response_model=list[PipelineEventResponse],
    include_in_schema=False,
)
@limiter.limit("60/minute")
def pipeline_events(
    request: Request,
    session: Session = Depends(get_db_session),
) -> list[PipelineEventResponse]:
    repository = Customer360Repository(session)

    try:
        sample_customer_ids = tuple(repository.list_customer_ids(limit=10))
    except RepositoryError:
        session.rollback()
        sample_customer_ids = ()

    entries = build_event_stream(
        datetime.now(UTC), sample_customer_ids=sample_customer_ids
    )
    return [PipelineEventResponse.model_validate(entry) for entry in entries]


@app.get(
    "/demo/api/pipeline/services",
    response_model=list[PipelineServiceResponse],
    include_in_schema=False,
)
@limiter.limit("30/minute")
def pipeline_services(
    request: Request,
    session: Session = Depends(get_db_session),
) -> list[PipelineServiceResponse]:
    customer_count, _outbox_pending, db_reachable = _real_pipeline_inputs(session)
    now = datetime.now(UTC)
    kpis = compute_kpis(now, real_customer_count=customer_count)
    services = build_service_health(now, db_reachable=db_reachable, kpis=kpis)
    overlaid = _apply_engine_overlay_to_services(services)
    return [PipelineServiceResponse.model_validate(service) for service in overlaid]


@app.get(
    "/demo/api/pipeline/charts",
    response_model=PipelineChartsResponse,
    include_in_schema=False,
)
@limiter.limit("30/minute")
def pipeline_charts(
    request: Request,
    session: Session = Depends(get_db_session),
) -> PipelineChartsResponse:
    customer_count, _outbox_pending, _db_reachable = _real_pipeline_inputs(session)
    now = datetime.now(UTC)
    kpis = compute_kpis(now, real_customer_count=customer_count)
    charts = build_charts(now, real_customer_count=customer_count, kpis=kpis)
    return PipelineChartsResponse.model_validate(charts)


@app.get(
    "/demo/api/pipeline/customer/{customer_id}",
    response_model=list[PipelineCustomerFlowStepResponse],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Customer not found",
        },
    },
    include_in_schema=False,
)
@limiter.limit("120/minute")
def pipeline_customer_flow(
    request: Request,
    customer_id: str = Path(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
    session: Session = Depends(get_db_session),
) -> list[PipelineCustomerFlowStepResponse]:
    repository = Customer360Repository(session)
    profile = repository.get_by_customer_id(customer_id)

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    steps = build_customer_flow(customer_id, profile.created_at)
    return [PipelineCustomerFlowStepResponse.model_validate(step) for step in steps]


# ---------------------------------------------------------------------------
# Pipeline Control Center -- interactive actions layered on top of the
# passive dashboard above. See customer360/api/pipeline_simulation_engine.py
# for why this needs real (in-process, shared) state, unlike everything
# else on this page.
# ---------------------------------------------------------------------------


def _engine_real_customer_ids(session: Session) -> tuple[str, ...]:
    try:
        return tuple(Customer360Repository(session).list_customer_ids(limit=10))
    except RepositoryError:
        session.rollback()
        return ()


def _engine_session_or_none(session: Session) -> Session | None:
    _customer_count, _outbox_pending, db_reachable = _real_pipeline_inputs(session)
    return session if db_reachable else None


@app.post(
    "/demo/api/pipeline/generate",
    response_model=EventTraceResponse,
    include_in_schema=False,
)
@limiter.limit("20/minute")
def pipeline_generate_event(
    request: Request,
    session: Session = Depends(get_db_session),
) -> EventTraceResponse:
    trace = ENGINE.generate_event(
        session=_engine_session_or_none(session),
        real_customer_ids=_engine_real_customer_ids(session),
    )
    return EventTraceResponse.model_validate(trace)


@app.post(
    "/demo/api/pipeline/replay",
    response_model=EventTraceResponse,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "No event has been generated yet",
        },
    },
    include_in_schema=False,
)
@limiter.limit("30/minute")
def pipeline_replay_event(request: Request) -> EventTraceResponse:
    try:
        trace = ENGINE.replay_last_event()
    except PipelineEngineError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return EventTraceResponse.model_validate(trace)


@app.post(
    "/demo/api/pipeline/failure",
    response_model=EventTraceResponse,
    include_in_schema=False,
)
@limiter.limit("20/minute")
def pipeline_inject_failure(
    request: Request,
    body: InjectFailureRequest,
    session: Session = Depends(get_db_session),
) -> EventTraceResponse:
    trace = ENGINE.inject_failure(
        body.failure_type,
        session=_engine_session_or_none(session),
        real_customer_ids=_engine_real_customer_ids(session),
    )
    return EventTraceResponse.model_validate(trace)


@app.post(
    "/demo/api/pipeline/retry",
    response_model=EventTraceResponse,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "No failed event to retry",
        },
    },
    include_in_schema=False,
)
@limiter.limit("30/minute")
def pipeline_retry_event(
    request: Request,
    session: Session = Depends(get_db_session),
) -> EventTraceResponse:
    try:
        trace = ENGINE.retry_failed_event(session=_engine_session_or_none(session))
    except PipelineEngineError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return EventTraceResponse.model_validate(trace)


@app.post(
    "/demo/api/pipeline/recover",
    response_model=PipelineStateResponse,
    include_in_schema=False,
)
@limiter.limit("20/minute")
def pipeline_recover_consumer(request: Request) -> PipelineStateResponse:
    state = ENGINE.recover_consumer()
    return PipelineStateResponse.model_validate(state)


@app.post(
    "/demo/api/pipeline/reset",
    response_model=PipelineStateResponse,
    include_in_schema=False,
)
@limiter.limit("6/minute")
def pipeline_reset_demo(
    request: Request,
    session: Session = Depends(get_db_session),
) -> PipelineStateResponse:
    state = ENGINE.reset(session=_engine_session_or_none(session))
    return PipelineStateResponse.model_validate(state)


@app.get(
    "/demo/api/pipeline/state",
    response_model=PipelineStateResponse,
    include_in_schema=False,
)
@limiter.limit("60/minute")
def pipeline_get_state(request: Request) -> PipelineStateResponse:
    return PipelineStateResponse.model_validate(ENGINE.get_state())


app.include_router(v1)