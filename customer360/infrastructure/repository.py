from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import select
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

    def create(self, profile: Customer360Profile) -> Customer360Profile:
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
                extra={"customer_id": getattr(profile, "customer_id", None)},
            )

            raise RepositoryError(
                "Unable to create Customer 360 profile."
            ) from exc

    def get_by_customer_id(
        self,
        customer_id: str,
    ) -> Customer360Profile | None:
        try:
            statement = (
                select(Customer360Profile)
                .where(Customer360Profile.customer_id == customer_id)
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
            statement = (
                select(Customer360Profile)
                .order_by(
                    Customer360Profile.total_spend.desc(),
                    Customer360Profile.customer_id,
                )
            )

            return self._session.scalars(statement).all()

        except SQLAlchemyError as exc:
            logger.exception("Failed to list Customer 360 profiles")

            raise RepositoryError(
                "Unable to list Customer 360 profiles."
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
                extra={"customer_id": updated_profile.customer_id},
            )

            return updated_profile

        except SQLAlchemyError as exc:
            self._session.rollback()

            logger.exception(
                "Failed to update Customer 360 profile",
                extra={"customer_id": getattr(profile, "customer_id", None)},
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