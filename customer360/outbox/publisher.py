from __future__ import annotations

import logging

from customer360.messaging.producer import CustomerEventProducer
from customer360.messaging.schemas import CustomerEvent
from customer360.outbox.repository import OutboxRepository

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(
        self,
        repository: OutboxRepository,
        producer: CustomerEventProducer,
    ) -> None:
        self.repository = repository
        self.producer = producer

    def publish_pending(self) -> int:
        published = 0

        for record in self.repository.pending():
            try:
                event = CustomerEvent.model_validate_json(record.payload)
                self.producer.publish(event)
                self.repository.mark_published(record)
                published += 1

            except Exception:
                logger.exception(
                    "Failed publishing outbox event %s",
                    record.event_id,
                )
                self.repository.increment_retry(record)

        self.producer.flush()

        return published