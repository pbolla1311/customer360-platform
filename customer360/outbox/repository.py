from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from customer360.outbox.models import OutboxEvent


class OutboxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        event_id: str,
        event_type: str,
        payload: str,
    ) -> OutboxEvent:
        event = OutboxEvent(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
        )
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def pending(self) -> list[OutboxEvent]:
        now = datetime.now(UTC).replace(tzinfo=None)

        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "PENDING",
                OutboxEvent.dead_lettered.is_(False),
                (
                    (OutboxEvent.next_retry_at.is_(None))
                    | (OutboxEvent.next_retry_at <= now)
                ),
            )
            .order_by(OutboxEvent.id)
        )

        return list(self.session.scalars(stmt))

    def increment_retry(self, event: OutboxEvent) -> None:
        event.retry_count += 1

        if event.retry_count >= event.max_retries:
            event.dead_lettered = True
            event.status = "FAILED"
        else:
            delay = 2 ** event.retry_count
            event.next_retry_at = (
                datetime.now(UTC).replace(tzinfo=None)
                + timedelta(seconds=delay)
            )

        self.session.commit()

    def mark_published(self, event: OutboxEvent) -> None:
        event.status = "PUBLISHED"
        event.published_at = datetime.now(UTC).replace(tzinfo=None)
        event.next_retry_at = None
        self.session.commit()