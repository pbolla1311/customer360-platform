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

## Pipeline Control Center (v1.2)

`pipeline_telemetry.py` above is a pure function of time -- no memory
between requests, by design. The Control Center toolbar on
`/demo/pipeline` (Generate/Replay/Inject Failure/Retry/Recover/Reset)
needs the opposite: an action in one HTTP request must be visible in a
later, separate request. That real, cross-request state lives in one
place only:

                    POST /demo/api/pipeline/{generate,replay,
                         failure,retry,recover,reset}
                    GET  /demo/api/pipeline/state
                              │
                              ▼
                 PipelineSimulationEngine (singleton)
          thread-safe, in-memory, shared by every visitor --
          the single source of truth for interactive state
                              │
              ┌───────────────┴───────────────┐
              ▼                                ▼
   best-effort mirror via the            additively overlaid onto
   existing, unmodified                  pipeline_telemetry.py's
   OutboxRepository.add() /              ambient summary/services
   mark_published() /                    output, inside main.py --
   increment_retry()                     pipeline_telemetry.py itself
   (real outbox_events row,              was not modified; at the
   only when the DB is                   engine's idle state every
   reachable; never required)            delta is 0 (no-op overlay)

No `random` calls anywhere in `pipeline_simulation_engine.py`: event
type/customer selection cycles off a sequence counter, and retry
resolution is a deterministic rule (succeeds iff `consumer_healthy`,
else increments toward a fixed `max_retries` before routing to the DLQ)
-- not a coin flip. See README -> Pipeline Control Center for the full
reasoning and the one caveat worth knowing before relying on this in a
demo with concurrent visitors: the engine is global, not per-session.
