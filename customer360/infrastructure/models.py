from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from customer360.infrastructure.session import Base


class Customer360Profile(Base):
    __tablename__ = "customer360_profiles"

    customer_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )
    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    state: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    transaction_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    total_spend: Mapped[float] = mapped_column(
        Float,
        default=0.0,
    )
    average_transaction_value: Mapped[float] = mapped_column(
        Float,
        default=0.0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
