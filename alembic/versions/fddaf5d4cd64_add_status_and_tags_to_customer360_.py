"""add status and tags to customer360 profiles

Revision ID: fddaf5d4cd64
Revises: 1811e890ede7
Create Date: 2026-07-27 22:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fddaf5d4cd64"
down_revision: str | Sequence[str] | None = "1811e890ede7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customer360_profiles",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "customer360_profiles",
        sa.Column(
            "tags",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("customer360_profiles", "tags")
    op.drop_column("customer360_profiles", "status")
