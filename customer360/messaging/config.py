from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class KafkaSettings:
    bootstrap_servers: str
    topic: str
    consumer_group: str
    auto_offset_reset: str

    @classmethod
    def from_env(cls) -> "KafkaSettings":
        return cls(
            bootstrap_servers=os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS",
                "localhost:9092",
            ),
            topic=os.getenv(
                "KAFKA_TOPIC",
                "customer360.customer-events.v1",
            ),
            consumer_group=os.getenv(
                "KAFKA_CONSUMER_GROUP",
                "customer360-profile-consumer",
            ),
            auto_offset_reset=os.getenv(
                "KAFKA_AUTO_OFFSET_RESET",
                "earliest",
            ),
        )