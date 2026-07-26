from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status

from customer360.config import API_TITLE, API_VERSION
from customer360.infrastructure.models import Customer360Profile
from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import get_db_session

app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
)

v1 = APIRouter(prefix="/api/v1", tags=["v1"])


def serialize_profile(profile: Customer360Profile) -> dict[str, object]:
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


@app.get("/")
def root() -> dict[str, str]:
    return {
        "application": "Customer360 Platform",
        "status": "running",
        "version": API_VERSION,
    }


@app.get("/health")
@v1.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "version": API_VERSION,
    }


@app.get("/ready")
@v1.get("/ready")
def readiness(
    session: Session = Depends(get_db_session),
) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc

    return {
        "status": "ready",
        "database": "connected",
        "version": API_VERSION,
    }


@app.get("/customers")
@v1.get("/customers")
def get_customers(
    session: Session = Depends(get_db_session),
) -> list[dict[str, object]]:
    repository = Customer360Repository(session)
    profiles = repository.list_all()
    return [serialize_profile(profile) for profile in profiles]


@app.get("/customers/{customer_id}")
@v1.get("/customers/{customer_id}")
def get_customer(
    customer_id: str,
    session: Session = Depends(get_db_session),
) -> dict[str, object]:
    repository = Customer360Repository(session)
    profile = repository.get_by_customer_id(customer_id)

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    return serialize_profile(profile)


app.include_router(v1)