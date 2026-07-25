from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from confluent_kafka import KafkaException, Producer

from customer360.messaging.config import KafkaSettings
from customer360.messaging.schemas import CustomerEvent

logger = logging.getLogger(__name__)


class CustomerEventProducer:
    def __init__(
        self,
        settings: Optional[KafkaSettings] = None,
        producer: Optional[Producer] = None,
    ) -> None:
        self.settings = settings or KafkaSettings.from_env()
        self._producer = producer or Producer(
            {
                "bootstrap.servers": self.settings.bootstrap_servers,
                "client.id": "customer360-producer",
                "enable.idempotence": True,
                "acks": "all",
            }
        )

    @staticmethod
    def _delivery_callback(error: Any, message: Any) -> None:
        if error is not None:
            logger.error(
                "Kafka delivery failed",
                extra={"error": str(error)},
            )
            return

        logger.info(
            "Kafka event delivered",
            extra={
                "topic": message.topic(),
                "partition": message.partition(),
                "offset": message.offset(),
            },
        )

    def publish(self, event: CustomerEvent) -> None:
        try:
            self._producer.produce(
                topic=self.settings.topic,
                key=event.payload.customer_id.encode("utf-8"),
                value=event.model_dump_json().encode("utf-8"),
                on_delivery=self._delivery_callback,
            )
            self._producer.poll(0)
        except BufferError as exc:
            logger.exception("Kafka producer queue is full")
            raise KafkaException(str(exc)) from exc
        except KafkaException:
            logger.exception("Kafka event publish failed")
            raise

    def flush(self, timeout: float = 10.0) -> None:
        remaining = self._producer.flush(timeout)

        if remaining > 0:
            raise KafkaException(
                f"{remaining} Kafka message(s) were not delivered before timeout"
            )

    def close(self) -> None:
        self.flush()