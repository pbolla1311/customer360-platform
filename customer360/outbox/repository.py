from __future__ import annotations

from datetime import datetime, timezone

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
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "PENDING",
                OutboxEvent.dead_lettered.is_(False),
            )
            .order_by(OutboxEvent.id)
        )
        return list(self.session.scalars(stmt))

    def increment_retry(self, event: OutboxEvent) -> None:
        event.retry_count += 1

        if event.retry_count >= event.max_retries:
            event.dead_lettered = True
            event.status = "FAILED"

        self.session.commit()

    def mark_published(self, event: OutboxEvent) -> None:
        event.status = "PUBLISHED"
        event.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.session.commit()