"""baseline existing customer360 profiles table

Revision ID: b8584a766c1f
Revises:
Create Date: 2026-07-25 15:35:26.839126
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8584a766c1f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer360_profiles",
        sa.Column(
            "customer_id",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "first_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "last_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "city",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "state",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "transaction_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "total_spend",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "average_transaction_value",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("customer_id"),
    )

    op.create_index(
        op.f("ix_customer360_profiles_email"),
        "customer360_profiles",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_customer360_profiles_email"),
        table_name="customer360_profiles",
    )
    op.drop_table("customer360_profiles")