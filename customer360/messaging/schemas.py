from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class CustomerEventType(StrEnum):
    CREATED = "customer.created"
    UPDATED = "customer.updated"
    UPSERTED = "customer.upserted"


class CustomerProfilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(min_length=1)
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    city: str | None = None
    state: str | None = None
    transaction_count: int = Field(ge=0)
    total_spend: float = Field(ge=0)
    average_transaction_value: float = Field(ge=0)


class CustomerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    event_type: CustomerEventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = "customer360-platform"
    payload: CustomerProfilePayload