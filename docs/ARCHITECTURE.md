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

## Workspace Shell (Customer360 Cloud, v2.0)

`/workspace` is a single-page, sidebar-navigated shell (Overview,
Customers, Event Center, Pipeline, Monitoring, Analytics, Audit Logs, API
Explorer, Settings) layered entirely on top of the pieces above -- it
introduces two new endpoints and two new engine methods, and otherwise
composes existing routes/data. `/demo`, `/demo/pipeline`, and every
`/demo/api/*` route are unmodified and still work standalone.

The one genuinely new capability is a real customer edit that produces a
real event, instead of the Control Center's manual "Generate Customer
Event" button:

                PATCH /demo/api/customers/{customer_id}
                              │
                 Customer360Repository.update()
                (existing method, real Postgres write)
                              │
                 diff which field(s) actually changed
              (email / city+state / else "Customer Updated")
                              │
              ENGINE.record_customer_update(customer_id, event_type)
        (new method: same happy-path trace shape as generate_event,
         always succeeds -- failures stay an explicit Control Center
         action -- and best-effort mirrors a real outbox_events row via
         the existing OutboxRepository, exactly like generate_event does)
                              │
                              ▼
              GET /demo/api/pipeline/history (new, new)
      (ENGINE.get_trace_history(): most-recent-first list of every
       event this engine has produced -- Control Center actions AND
       real customer edits alike -- each with its full per-stage trace)
                              │
              ┌───────────────┼───────────────────────────┐
              ▼               ▼                           ▼
       Event Center     Audit Logs                  Customers timeline
    (event-level table) (step-level trace:      (same history, filtered
                         Producer→Kafka Topic→     to one customer_id)
                         Outbox→Consumer→
                         PostgreSQL, or Retry
                         Queue/DLQ on failure)

Everything else in the shell reuses existing read-only endpoints without
any new backend code:

| Workspace view | Backend source |
| --------------- | --------------- |
| Overview        | `/demo/api/summary`, `/demo/api/pipeline/summary`, `/demo/api/pipeline/services`, `/demo/api/pipeline/history`, `/demo/api/customers` (client-side aggregation) |
| Customers       | `/demo/api/customers`, `/demo/api/customers/{id}`, new `PATCH .../{id}`, `/demo/api/pipeline/history` (client-filtered by customer) |
| Pipeline        | Same-origin `<iframe src="/demo/pipeline">` -- the existing dashboard, byte-for-byte. Parent JS reaches into the same-origin `iframe.contentDocument` after load to hide the page's own header and the "Generate Customer Event" button only (real edits already produce events); wrapped in try/catch so a structural change to `pipeline/index.html` degrades to "show the full page" rather than breaking |
| Monitoring      | `/demo/api/pipeline/summary`, `/services`, plus `history` for a "Recent Failures" list |
| Analytics       | `/demo/api/customers` (revenue/growth/state/top-customers, all computed client-side from real rows) + `/demo/api/pipeline/charts` (`top_event_types`, simulated) |
| Audit Logs      | `/demo/api/pipeline/history` at step level |
| API Explorer    | Same-origin `<iframe src="/docs">` -- `/docs` itself is unchanged and still directly reachable for developers/tooling |
| Settings        | `/health`, `/status`, and the existing `POST /demo/api/pipeline/reset` |

Like the Control Center, the workspace's ambient KPI numbers (throughput,
messages processed, etc.) remain `pipeline_telemetry.py`'s existing
time-seeded simulation -- a real customer edit is reflected precisely
(its own event, trace, and timeline entry), the same way the Control
Center's own actions have always been layered on top of that ambient
simulation rather than replacing it.
