from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from customer360.api.security import verify_api_key
from customer360.config import API_TITLE, API_VERSION
from customer360.infrastructure.models import Customer360Profile
from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import get_db_session


class RootResponse(BaseModel):
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
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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


@app.get(
    "/",
    response_model=RootResponse,
    summary="Application status",
)
def root() -> RootResponse:
    return RootResponse(
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
    customer_id: str,
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