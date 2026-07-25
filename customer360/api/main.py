from sqlalchemy.orm import Session
from fastapi import Depends, FastAPI, HTTPException

from customer360.config import API_TITLE, API_VERSION
from customer360.infrastructure.models import Customer360Profile
from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import get_db_session

app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
)


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
    }


@app.get("/customers")
def get_customers(
    session: Session = Depends(get_db_session),
) -> list[dict[str, object]]:
    repository = Customer360Repository(session)
    profiles = repository.list_all()

    return [serialize_profile(profile) for profile in profiles]


@app.get("/customers/{customer_id}")
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