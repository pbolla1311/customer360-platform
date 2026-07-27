# Customer360 Enterprise Lakehouse Architecture

## High-Level Architecture

                        Public Datasets
                              │
                              ▼
                    Batch & Streaming Ingestion
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
     Batch Loader                         Event Producer
          │                                       │
          └───────────────────┬───────────────────┘
                              ▼
                       Bronze Data Layer
                              │
                              ▼
                       Spark Transformations
                              │
                 Bronze → Silver → Gold
                              │
                              ▼
                    PostgreSQL Analytics
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
     FastAPI REST API                   Streamlit Dashboard

## Demo & Pipeline Monitoring Layer

`/demo` and `/demo/pipeline` are unauthenticated, read-only views layered on
top of the same FastAPI process and PostgreSQL database as the real API --
not a separate service, and not the Streamlit dashboard referenced above.

                 PostgreSQL (customer360_profiles, outbox_events)
                              │
                              ▼
              Customer360Repository / OutboxRepository
                    (same repository layer as /api/v1/*)
                              │
              ┌───────────────┴───────────────┐
              ▼                                ▼
      /demo/api/* (v1.1)              /demo/api/pipeline/* (this feature)
   customers, summary, search      summary, events, services, charts,
                                          customer/{id}
              │                                │
              ▼                                ▼
       /demo dashboard                  pipeline_telemetry.py
     (real customer data)          deterministic, time-seeded simulator
                                   for Kafka/outbox/retry/DLQ telemetry
                                   that has no live backing in this
                                   deployment (see README -> Pipeline
                                   Monitor and -> Limitations)
                                                │
                                                ▼
                                   /demo/pipeline dashboard
                              (KPI cards, flow viz, charts, service
                               health, illustrative customer event flow)

Real vs. simulated at a glance:

| Real (from PostgreSQL)                          | Simulated (`pipeline_telemetry.py`)         |
| ------------------------------------------------ | -------------------------------------------- |
| Total customers / transactions                   | Kafka throughput, events/sec, consumer lag   |
| `outbox_events` row count, if any exist           | Retry queue depth, DLQ depth                 |
| Database reachability (`SELECT 1`)                | Kafka/Consumer/Outbox/Scheduler service health |
| `PostgreSQL` pipeline stage count                 | Producer/Kafka Topic/Outbox/Consumer/Retry/DLQ stage counts |
| A selected customer's real `created_at`           | The rest of that customer's event-flow timeline |
