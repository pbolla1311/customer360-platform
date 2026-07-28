from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# Customer360Profile.organization_id (below) references "organizations.id",
# defined in customer360.tenancy.models -- a separate module on the same
# shared Base.metadata. Importing it here (side-effect only) guarantees
# that table is always registered before any Base.metadata.create_all()
# runs, regardless of which module happens to import this one first.
import customer360.tenancy.models  # noqa: F401,E402
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
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
    )
    tags: Mapped[str] = mapped_column(
        Text,
        default="[]",
    )
    # Nullable: existing rows/ingestion paths that never specify an
    # organization keep working unchanged (v3.5 multi-tenancy). Backfilled
    # for all pre-existing rows by the migration that added this column.
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=True,
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
