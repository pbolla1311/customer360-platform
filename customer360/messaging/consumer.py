from __future__ import annotations

import logging
from typing import Iterator, Optional

from confluent_kafka import Consumer

from customer360.messaging.config import KafkaSettings
from customer360.messaging.schemas import CustomerEvent

logger = logging.getLogger(__name__)


class CustomerEventConsumer:
    def __init__(
        self,
        settings: Optional[KafkaSettings] = None,
    ) -> None:
        self.settings = settings or KafkaSettings.from_env()

        self._consumer = Consumer(
            {
                "bootstrap.servers": self.settings.bootstrap_servers,
                "group.id": self.settings.consumer_group,
                "auto.offset.reset": self.settings.auto_offset_reset,
            }
        )

        self._consumer.subscribe([self.settings.topic])

    def consume(self, timeout: float = 1.0) -> Iterator[CustomerEvent]:
        while True:
            message = self._consumer.poll(timeout)

            if message is None:
                continue

            if message.error():
                logger.error("Kafka consumer error: %s", message.error())
                continue

            yield CustomerEvent.model_validate_json(message.value())

    def close(self) -> None:
        self._consumer.close()