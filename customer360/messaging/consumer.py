from __future__ import annotations

import logging
from collections.abc import Iterator
from uuid import UUID

from confluent_kafka import Consumer

from customer360.messaging.config import KafkaSettings
from customer360.messaging.schemas import CustomerEvent

logger = logging.getLogger(__name__)


class CustomerEventConsumer:
    def __init__(
        self,
        settings: KafkaSettings | None = None,
    ) -> None:
        self.settings = settings or KafkaSettings.from_env()

        self._consumer = Consumer(
            {
                "bootstrap.servers": self.settings.bootstrap_servers,
                "group.id": self.settings.consumer_group,
                "auto.offset.reset": self.settings.auto_offset_reset,
                "enable.auto.commit": False,
            }
        )

        self._consumer.subscribe([self.settings.topic])

        self._processed_event_ids: set[UUID] = set()

    def consume(self, timeout: float = 1.0) -> Iterator[CustomerEvent]:
        while True:
            message = self._consumer.poll(timeout)

            if message is None:
                continue

            if message.error():
                logger.error("Kafka consumer error: %s", message.error())
                continue

            message_value = message.value()

            if message_value is None:
                logger.warning("Skipping Kafka message with an empty value")
                self._consumer.commit(message=message)
                continue

            event = CustomerEvent.model_validate_json(message_value)

            if event.event_id in self._processed_event_ids:
                logger.info("Skipping duplicate event %s", event.event_id)
                self._consumer.commit(message=message)
                continue

            self._processed_event_ids.add(event.event_id)

            yield event

            self._consumer.commit(message=message)

    def close(self) -> None:
        self._consumer.close()