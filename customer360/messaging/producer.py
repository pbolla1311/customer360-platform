from __future__ import annotations

import logging
from typing import Any, Optional

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
            logger.error("Kafka delivery failed", extra={"error": str(error)})
            return

        logger.info(
            "Kafka event delivered",
            extra={
                "topic": message.topic(),
                "partition": message.partition(),
                "offset": message.offset(),
            },
        )

    def publish(
        self,
        event: CustomerEvent,
        topic: Optional[str] = None,
    ) -> None:
        try:
            self._producer.produce(
                topic=topic or self.settings.topic,
                key=event.payload.customer_id.encode(),
                value=event.model_dump_json().encode(),
                on_delivery=self._delivery_callback,
            )
            self._producer.poll(0)

        except BufferError as exc:
            logger.exception("Kafka producer queue full")
            raise KafkaException(str(exc)) from exc

        except KafkaException:
            logger.exception("Kafka publish failed")

            # Publish to dead-letter topic
            if topic != f"{self.settings.topic}.dlq":
                self.publish(
                    event,
                    topic=f"{self.settings.topic}.dlq",
                )

            raise

    def flush(self, timeout: float = 10.0) -> None:
        remaining = self._producer.flush(timeout)

        if remaining:
            raise KafkaException(
                f"{remaining} Kafka message(s) were not delivered before timeout"

            )
            

    def close(self) -> None:
        self.flush()