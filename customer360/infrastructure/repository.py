from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from customer360.infrastructure.models import Customer360Profile

logger = logging.getLogger(__name__)


class RepositoryError(RuntimeError):
    """Raised when a repository operation fails."""


class Customer360Repository:
    """SQLAlchemy repository for Customer 360 profiles."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        profile: Customer360Profile,
    ) -> Customer360Profile:
        try:
            self._session.add(profile)
            self._session.commit()
            self._session.refresh(profile)

            logger.info(
                "Created Customer 360 profile",
                extra={"customer_id": profile.customer_id},
            )

            return profile

        except SQLAlchemyError as exc:
            self._session.rollback()

            logger.exception(
                "Failed to create Customer 360 profile",
                extra={
                    "customer_id": getattr(
                        profile,
                        "customer_id",
                        None,
                    )
                },
            )

            raise RepositoryError(
                "Unable to create Customer 360 profile."
            ) from exc

    def get_by_customer_id(
        self,
        customer_id: str,
    ) -> Customer360Profile | None:
        try:
            statement = select(Customer360Profile).where(
                Customer360Profile.customer_id == customer_id
            )

            return self._session.scalar(statement)

        except SQLAlchemyError as exc:
            logger.exception(
                "Failed to retrieve Customer 360 profile",
                extra={"customer_id": customer_id},
            )

            raise RepositoryError(
                "Unable to retrieve Customer 360 profile."
            ) from exc

    def list_all(self) -> Sequence[Customer360Profile]:
        try:
            statement = select(Customer360Profile).order_by(
                Customer360Profile.total_spend.desc(),
                Customer360Profile.customer_id,
            )

            return self._session.scalars(statement).all()

        except SQLAlchemyError as exc:
            logger.exception(
                "Failed to list Customer 360 profiles"
            )

            raise RepositoryError(
                "Unable to list Customer 360 profiles."
            ) from exc

    def count_all(self) -> int:
        """Total profile row count via a single aggregate query.

        Distinct from list_all(): callers that only need a count (e.g. the
        /demo/pipeline dashboard) should use this instead of len(list_all()),
        which would fetch every column of every row just to discard them.
        """

        try:
            statement = select(func.count()).select_from(Customer360Profile)

            return self._session.scalar(statement) or 0

        except SQLAlchemyError as exc:
            logger.exception("Failed to count Customer 360 profiles")

            raise RepositoryError(
                "Unable to count Customer 360 profiles."
            ) from exc

    def list_customer_ids(self, limit: int = 10) -> Sequence[str]:
        """A handful of customer_ids only -- avoids fetching full rows for
        callers (e.g. the /demo/pipeline event stream) that just need a few
        IDs to reference, not every column."""

        try:
            statement = (
                select(Customer360Profile.customer_id)
                .order_by(Customer360Profile.customer_id)
                .limit(limit)
            )

            return self._session.scalars(statement).all()

        except SQLAlchemyError as exc:
            logger.exception("Failed to list Customer 360 customer IDs")

            raise RepositoryError(
                "Unable to list Customer 360 customer IDs."
            ) from exc

    def update(
        self,
        profile: Customer360Profile,
    ) -> Customer360Profile:
        try:
            updated_profile = self._session.merge(profile)

            self._session.commit()
            self._session.refresh(updated_profile)

            logger.info(
                "Updated Customer 360 profile",
                extra={
                    "customer_id": updated_profile.customer_id
                },
            )

            return updated_profile

        except SQLAlchemyError as exc:
            self._session.rollback()

            logger.exception(
                "Failed to update Customer 360 profile",
                extra={
                    "customer_id": getattr(
                        profile,
                        "customer_id",
                        None,
                    )
                },
            )

            raise RepositoryError(
                "Unable to update Customer 360 profile."
            ) from exc

    def delete(self, customer_id: str) -> bool:
        try:
            profile = self.get_by_customer_id(customer_id)

            if profile is None:
                return False

            self._session.delete(profile)
            self._session.commit()

            logger.info(
                "Deleted Customer 360 profile",
                extra={"customer_id": customer_id},
            )

            return True

        except SQLAlchemyError as exc:
            self._session.rollback()

            logger.exception(
                "Failed to delete Customer 360 profile",
                extra={"customer_id": customer_id},
            )

            raise RepositoryError(
                "Unable to delete Customer 360 profile."
            ) from exc

    def bulk_upsert(
        self,
        profiles: Sequence[Mapping[str, Any]],
        batch_size: int = 1000,
    ) -> int:
        """Insert or update Customer 360 profiles in batches."""

        if not profiles:
            return 0

        if batch_size <= 0:
            raise ValueError(
                "batch_size must be greater than zero"
            )

        total_processed = 0

        try:
            for start in range(
                0,
                len(profiles),
                batch_size,
            ):
                batch = profiles[
                    start : start + batch_size
                ]

                statement = insert(
                    Customer360Profile
                ).values(list(batch))

                statement = statement.on_conflict_do_update(
                    index_elements=[
                        Customer360Profile.customer_id
                    ],
                    set_={
                        "first_name": (
                            statement.excluded.first_name
                        ),
                        "last_name": (
                            statement.excluded.last_name
                        ),
                        "email": statement.excluded.email,
                        "city": statement.excluded.city,
                        "state": statement.excluded.state,
                        "transaction_count": (
                            statement.excluded.transaction_count
                        ),
                        "total_spend": (
                            statement.excluded.total_spend
                        ),
                        "average_transaction_value": (
                            statement.excluded
                            .average_transaction_value
                        ),
                        "updated_at": (
                            statement.excluded.updated_at
                        ),
                    },
                )

                self._session.execute(statement)
                self._session.commit()

                total_processed += len(batch)

                logger.info(
                    "Bulk upsert batch completed",
                    extra={
                        "batch_size": len(batch),
                        "total_processed": total_processed,
                    },
                )

            return total_processed

        except SQLAlchemyError as exc:
            self._session.rollback()

            logger.exception(
                "Bulk upsert failed",
                extra={
                    "total_processed": total_processed
                },
            )

            raise RepositoryError(
                "Unable to bulk upsert "
                "Customer 360 profiles."
            ) from exc