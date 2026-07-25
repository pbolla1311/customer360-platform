from __future__ import annotations

from customer360.messaging.producer import CustomerEventProducer
from customer360.messaging.schemas import CustomerEvent
from customer360.outbox.repository import OutboxRepository


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
            event = CustomerEvent.model_validate_json(record.payload)

            self.producer.publish(event)
            self.repository.mark_published(record)

            published += 1

        self.producer.flush()

        return published