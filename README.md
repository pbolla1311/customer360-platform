<div align="center">

# Customer360 Platform

**A production-style customer data platform demonstrating backend architecture, event-driven data engineering, and secure API design — built solo and deployed end to end.**

[![CI](https://github.com/pbolla1311/customer360-platform/actions/workflows/tests.yml/badge.svg)](https://github.com/pbolla1311/customer360-platform/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Type Checking](https://img.shields.io/badge/mypy-strict-2A6DB2?style=flat-square)](https://mypy-lang.org/)
[![Lint](https://img.shields.io/badge/lint-ruff-D7FF64?style=flat-square)](https://docs.astral.sh/ruff/)
[![Tests](https://img.shields.io/badge/tests-68%20passing-brightgreen?style=flat-square)](https://github.com/pbolla1311/customer360-platform/tree/main/tests)

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Kafka](https://img.shields.io/badge/Kafka-231F20?style=flat-square&logo=apachekafka&logoColor=white)](https://kafka.apache.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-CC2927?style=flat-square)](https://www.sqlalchemy.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-326CE5?style=flat-square&logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Terraform](https://img.shields.io/badge/Terraform-7B42BC?style=flat-square&logo=terraform&logoColor=white)](https://www.terraform.io/)
[![Railway](https://img.shields.io/badge/Railway-0B0D0E?style=flat-square&logo=railway&logoColor=white)](https://railway.app/)

</div>

---

## Live Demo

The API is deployed and publicly reachable on Railway.

| Resource | URL |
| --- | --- |
| Application root | <https://customer360-platform-production.up.railway.app> |
| Customer360 Cloud Workspace | <https://customer360-platform-production.up.railway.app/workspace> |
| Swagger UI | <https://customer360-platform-production.up.railway.app/docs> |
| ReDoc | <https://customer360-platform-production.up.railway.app/redoc> |
| OpenAPI schema | <https://customer360-platform-production.up.railway.app/openapi.json> |

> The `/customers` endpoints require an `X-API-Key` header, verified server-side against the `API_KEY` environment variable. That variable isn't currently set on the live Railway deployment, so `/customers` there returns `503 API security is not configured` rather than serving data — the endpoint fails closed instead of silently allowing access. It works end-to-end locally and in CI, where `API_KEY` is set. Everything else — root, health, readiness, docs, and the OpenAPI schema — is open on the live demo.

---

## Customer360 Cloud Workspace

_New in v2.0._ **[`/workspace`](https://customer360-platform-production.up.railway.app/workspace)** is the primary way to experience this platform: a single, sidebar-navigated SaaS-style workspace (Overview, Customers, Event Center, Pipeline, Monitoring, Analytics, Audit Logs, API Explorer, Settings) built entirely on top of the pieces documented below — it adds two new endpoints and reuses everything else.

**The one continuous story it tells:** editing a customer in the Customers view is a real write. Click Save and it:

1. Updates the real `customer360_profiles` row via the existing `Customer360Repository.update()`.
2. Determines what changed (email / city+state / name) and labels the resulting event `Email Changed`, `Address Changed`, or `Customer Updated` — the same vocabulary the Control Center's simulated events already use.
3. Calls a new `PipelineSimulationEngine.record_customer_update()` method — same happy-path trace shape as the Control Center's `generate_event()`, but for one specific real customer action, and it best-effort mirrors a real `outbox_events` row exactly the way `generate_event` already does.
4. That event immediately shows up in **Event Center** (event-level table), **Pipeline** (embedded Control Center — see below), **Monitoring**, **Audit Logs** (full per-stage trace: Producer → Kafka Topic → Outbox → Consumer → PostgreSQL), and the customer's own **Customer Timeline** — all reading one new endpoint, `GET /demo/api/pipeline/history`.

No "Generate Event" button anywhere in the workspace's Customers or Pipeline views — the event already exists, produced by the action that created it, matching a real product rather than a demo.

**How each view is actually built** (see `docs/ARCHITECTURE.md` → Workspace Shell for the full breakdown):

- **Overview / Monitoring / Analytics** — new client-side views over existing `/demo/api/*` and `/demo/api/pipeline/*` JSON endpoints (Analytics' revenue/growth/state/top-customer figures are computed in the browser from the real customer list, the same way `/demo`'s illustrative timeline was always computed client-side).
- **Pipeline** — a same-origin `<iframe src="/demo/pipeline">`, i.e. the exact existing dashboard, not a rebuild. Parent JS hides that page's own header and "Generate Customer Event" button after load (same-origin `contentDocument` access, wrapped in try/catch so it degrades safely) since the workspace's events already exist by the time you'd want to look at them; Inject Failure/Retry/Replay/Recover/Reset stay untouched as operational tools.
- **API Explorer** — a same-origin `<iframe src="/docs">`. `/docs` is unchanged and still directly reachable for developers and tooling.
- **Audit Logs** — the same `/demo/api/pipeline/history` response rendered at step level instead of event level.

**Nothing about `/demo`, `/demo/api/*`, `/demo/pipeline`, or `/demo/api/pipeline/*` changed.** Both keep working exactly as documented below — they're no longer the primary entry point (the landing page's main call to action is now "Open Workspace"), but they're kept live for backward compatibility and are linked from the workspace's own Settings view.

---

## Demo Dashboard

> **Legacy, still live.** Superseded as the primary experience by the Customers view in [Customer360 Cloud Workspace](#customer360-cloud-workspace) above — kept working unchanged for backward compatibility.

_New in v1.1._ **[`/demo`](https://customer360-platform-production.up.railway.app/demo)** is an interactive, recruiter-facing dashboard on top of the same FastAPI backend and PostgreSQL database as the rest of the platform — search customer profiles, select one, and view its fields, without needing an API key or reading raw JSON.

**Why it doesn't call `/api/v1/customers` directly:** that endpoint requires the `X-API-Key` secret (see the note above), and browser-side JavaScript can never hold that secret safely. So `/demo` is backed by its own read-only, unauthenticated routes — `GET /demo/api/summary`, `GET /demo/api/customers`, `GET /demo/api/customers/{customer_id}` — implemented in `customer360/api/main.py` right alongside the versioned routes, reusing the exact same `Customer360Repository` and serialization logic. They are excluded from the OpenAPI schema (like `/docs`/`/redoc`/`/`) since they exist only to support this page, not as a documented product API. **The real `/customers` and `/api/v1/customers*` endpoints are completely unchanged** — still key-gated, still rate-limited, still versioned.

**What's real data vs. illustrative demo data:**

| On the dashboard | Source |
| --- | --- |
| Total Customers, Total Transactions | Real — `COUNT(*)` / `SUM(transaction_count)` over `customer360_profiles` |
| Active Profiles | Real, but derived — profiles with `transaction_count > 0` (there's no `status` column in the schema) |
| Events Processed | **Sample metric** — the API has no live Kafka event count, so this is a labeled, deterministic function of the real transaction/customer counts, computed in the browser |
| Profile fields (ID, name, email, city, state, transaction count, spend, timestamps) | Real — whatever `customer360_profiles` actually has for that row |
| Activity Timeline | **Illustrative demo data** — generated entirely client-side in `demo.js` from the selected customer's ID (deterministic, not random, so it's stable across reloads); never a live transactions/events feed |

Every illustrative value on the page carries a visible "Sample metric" or "Illustrative demo data" tag, and the dashboard header shows a standing notice: _"Customer records are served from the live Customer360 API. Activity and selected summary metrics may use illustrative demo data where the backend does not yet expose those datasets."_

### Seeding fictional demo customers

The API is read-only over HTTP, so there's no write endpoint to populate `/demo` with data — instead, a script upserts a small fictional dataset directly through the repository layer:

```bash
ENABLE_DEMO_SEED=true python scripts/seed_demo_customers.py
# or:
python scripts/seed_demo_customers.py --force
```

- **Idempotent** — re-running it upserts the same 10 `customer_id`s (`DEMO-0001`..`DEMO-0010`) instead of creating duplicates.
- **Disabled by default** — it refuses to run unless `ENABLE_DEMO_SEED=true` or `--force` is passed explicitly; it is never invoked automatically by the app, a startup hook, or CI.
- **Fictional data only** — reserved example domains (`@example.com` / `@example.org`), invented names, no real personal information.
- If the database has no rows yet, `/demo` shows a professional empty state explaining that no demo records are loaded and linking to this command and to Swagger UI — it does not silently invent customers.

### Demo Dashboard Screenshot Checklist

<!-- Capture after seeding demo data (see above), then embed alongside the images in the Screenshots section below:
  - [ ] docs/images/demo-dashboard-desktop.png  — /demo at desktop width with a customer selected
  - [ ] docs/images/demo-dashboard-mobile.png   — /demo at a mobile viewport, no horizontal scroll
  - [ ] docs/images/demo-dashboard-empty.png    — /demo empty state (unseeded database)
-->

### v1.1 scope and limitations

- The dashboard is read-focused: search, select, view. There is no editing, and no write path was added anywhere in the API.
- "Active Profiles" and "Events Processed" are derived/illustrative as documented above — they are not new database columns or a new metrics pipeline.
- The Activity Timeline is frontend-only and does not reflect the Kafka event pipeline described elsewhere in this README; wiring a real per-customer event feed into `/demo` is future work (see [Roadmap](#roadmap)).
- `/demo/api/*` intentionally has no `X-API-Key` requirement — see "Why it doesn't call `/api/v1/customers` directly" above for the reasoning and its blast radius (read-only, seeded/fictional data only).

---

## Pipeline Monitor

> **Also embedded, unchanged, in the Pipeline tab of [Customer360 Cloud Workspace](#customer360-cloud-workspace)** (same-origin `<iframe>`, not a rebuild) — this standalone page still works exactly as documented below.

**[`/demo/pipeline`](https://customer360-platform-production.up.railway.app/demo/pipeline)** is an enterprise-monitoring-style dashboard (think Datadog/Confluent Cloud) built to make the platform's event-driven architecture — Kafka, the outbox pattern, retries, dead-lettering, observability — visible at a glance: 8 animated KPI cards, an animated 7-stage pipeline visualization (Producer → Kafka Topic → Outbox → Consumer → Retry Queue → Dead Letter Queue → PostgreSQL), a live-scrolling event stream, 6 charts (Chart.js, vendored locally — see below), 6 service health cards, and a per-customer illustrative event-flow timeline.

**Exact real-vs-simulated split** (the same distinction is shown on the page itself, via "Live data"/"Derived"/"Simulated" tags and a standing banner):

| Real, from PostgreSQL | Simulated, from `customer360/api/pipeline_telemetry.py` |
| --- | --- |
| The `PostgreSQL` pipeline stage (= real customer count) | The other 6 pipeline stages (Producer, Kafka Topic, Outbox, Consumer, Retry Queue, DLQ) |
| The `Database` and `API` service health cards | The `Kafka`, `Consumer`, `Outbox`, `Scheduler` service health cards |
| The `outbox_events` row count, if any exist | Retry queue depth, DLQ depth, events/sec, consumer lag, avg processing time |
| A selected customer's real `created_at` | The rest of that customer's "Profile Created → ... → Audit Logged" timeline |
| — | All 6 charts, and the entire live event stream |

**Why any of it is simulated at all:** Kafka isn't running on the live Railway deployment, there's no standalone `CustomerEventConsumer` worker deployed, and the `outbox_events` table has no live writers — all pre-existing facts already called out in [Limitations](#limitations), not something this feature changed. Rather than leave a "flagship" monitoring page either broken or fabricating arbitrary numbers, `pipeline_telemetry.py` is a **pure, deterministic function of a timestamp**: the same `now` always produces the same output (unit-tested directly, no FastAPI/DB/Kafka needed), values evolve smoothly across real wall-clock time via bounded sine-wave curves plus a time-bucketed seeded `random.Random` (never reseeded per request, so it's not noise), and the numbers are kept internally consistent by construction — `successful + failed == processed`, `retry_queue <= failed`, `dlq_messages <= failed`, latency and consumer lag stay in realistic bounded ranges. Nothing here is ever labeled as live production telemetry; every card and panel that isn't backed by a real query carries a visible "Simulated" tag, and the page has its own standing notice, same convention as `/demo`'s "Illustrative demo data" labels.

**Chart.js is vendored, not CDN-loaded.** `customer360/api/static/demo/vendor/chart.umd.min.js` is Chart.js 4.5.1 (MIT), downloaded once and committed, served from `/static/demo/vendor/chart.umd.min.js` — same pattern as the pre-existing vendored `swagger-ui-bundle.js` and `redoc.standalone.js`. This keeps the strict CSP (`script-src 'self'`, no `unsafe-eval`, no third-party origins) intact; nothing on `/demo/pipeline` makes a request to any CDN.

**New endpoints**, all unauthenticated for the same reason the rest of `/demo/api/*` is (see [Demo Dashboard](#demo-dashboard) above) and excluded from the OpenAPI schema:

| Method | Path | Description |
| :---: | --- | --- |
| `GET` | `/demo/pipeline` | The dashboard HTML page |
| `GET` | `/demo/api/pipeline/summary` | 8 KPIs + 7 pipeline stage counts/health |
| `GET` | `/demo/api/pipeline/events` | Rolling 12-entry simulated event stream |
| `GET` | `/demo/api/pipeline/services` | 6 service health cards |
| `GET` | `/demo/api/pipeline/charts` | 6 time-series/categorical series for the charts |
| `GET` | `/demo/api/pipeline/customer/{customer_id}` | 6-step illustrative event-flow timeline for one customer |

### Pipeline Control Center (v1.2)

The dashboard above is passive — it auto-refreshes but nothing a visitor does changes it. The **Control Center** toolbar on `/demo/pipeline` makes it interactive: **Generate Customer Event**, **Replay Last Event**, **Inject Failure**, **Retry Failed Event**, **Recover Consumer**, **Reset Demo**.

**Why this needed real state, unlike the rest of the page.** Everything above is a pure function of a timestamp — no memory between requests, by design. But "click Generate, then click Retry in a separate request and see the _same_ event" is impossible without something remembering what happened. `customer360/api/pipeline_simulation_engine.py` adds exactly that: one thread-safe, in-memory `PipelineSimulationEngine` singleton — the "single source of truth" the feature calls for. It's shared by every visitor, the same way a real shared ops dashboard would be (see [Limitations](#limitations) for what that means in practice). Nothing in it calls `random`: event types and customers cycle deterministically off a sequence counter, and per-stage processing times are fixed illustrative constants — every method is unit-tested with zero FastAPI/DB dependency.

**How retries actually resolve (no randomness, so this had to be a real rule, not a coin flip):** every failure type is modeled as manifesting through the one recovery lever this engine has — consumer health. Inject any of the 5 failure types and `consumer_healthy` goes false; **Retry** succeeds if and only if it's since gone true again via **Recover Consumer**. Retrying while still unhealthy increments the retry counter and stays failed; hitting `max_retries` (5 — the same default `OutboxEvent.max_retries` already uses) routes it to the DLQ instead. This is exactly the walkthrough in the task's own success criteria: generate → fail → retry (still failing) → DLQ _or_ recover → retry (succeeds).

**Persistence is real when the database is reachable, and never required.** `generate`/`failure`/`retry` mirror their outcome into a genuine `outbox_events` row using the _existing, already-tested_ `OutboxRepository.add()` / `mark_published()` / `increment_retry()` — no outbox business logic was duplicated to build this. That write is strictly best-effort: the in-memory engine is always the actual source of truth, so a database outage degrades to pure in-memory simulation rather than breaking the interactive flow. **Reset Demo** deletes only the specific rows this engine created (tracked by event ID) — it never touches real customer records or any other outbox row.

**The passive dashboard's numbers move too.** `/demo/api/pipeline/summary` and `/services` additively overlay the engine's counters onto the ambient (time-based) values from `pipeline_telemetry.py` — that file was not modified to build this; the overlay lives entirely in `main.py`. At the engine's initial/reset state every delta is 0, so the overlay is a byte-for-byte no-op — confirmed by a regression test that pins the idle-state shape.

New endpoints, same unauthenticated/excluded-from-schema treatment as the rest of `/demo/api/*`, but rate-limited tighter since they do real (if bounded) work — `reset` especially, since it clears state every visitor shares:

| Method | Path | Rate limit | Description |
| :---: | --- | :---: | --- |
| `POST` | `/demo/api/pipeline/generate` | 20/min | Generates the next event, delivers it end to end |
| `POST` | `/demo/api/pipeline/replay` | 30/min | Re-plays the last trace; no new writes |
| `POST` | `/demo/api/pipeline/failure` | 20/min | Body: `{"failure_type": "consumer_failure" \| "kafka_timeout" \| "database_timeout" \| "serialization_error" \| "validation_failure"}` |
| `POST` | `/demo/api/pipeline/retry` | 30/min | Retries the current failed event (409 if none) |
| `POST` | `/demo/api/pipeline/recover` | 20/min | Marks the Consumer healthy again |
| `POST` | `/demo/api/pipeline/reset` | 6/min | Restores idle state; deletes only this engine's outbox rows |
| `GET` | `/demo/api/pipeline/state` | 60/min | Current engine state, for syncing button enablement on load |

### Pipeline Monitor screenshot checklist

<!-- Capture after seeding demo data, then embed alongside the images in the Screenshots section below:
  - [ ] docs/images/pipeline-monitor-desktop.png — /demo/pipeline at desktop width, charts loaded
  - [ ] docs/images/pipeline-monitor-mobile.png  — /demo/pipeline at a mobile viewport, no horizontal scroll
-->

---

## Screenshots

<div align="center">

<img src="docs/images/social-preview.png" alt="Customer360 Platform — enterprise backend and data engineering" width="820"/>

<br/><br/>

<img src="docs/images/architecture.png" alt="System architecture diagram: FastAPI service, PostgreSQL, batch pipeline, and Kafka" width="820"/>
<br/><sub><b>System architecture</b> — see the interactive version in <a href="#architecture-diagram">Architecture Diagram</a></sub>

<br/><br/>

<img src="docs/images/swagger-ui.png" alt="Self-hosted Swagger UI showing the Customer360 Platform endpoint list" width="820"/>
<br/><sub><b>Swagger UI</b> — self-hosted at <code>/docs</code>, no external CDN, strict CSP</sub>

<br/><br/>

<img src="docs/images/redoc.png" alt="Self-hosted ReDoc documentation view" width="820"/>
<br/><sub><b>ReDoc</b> — self-hosted at <code>/redoc</code></sub>

<br/><br/>

<img src="docs/images/request-flow.png" alt="Request lifecycle sequence diagram" width="820"/>
<br/><sub><b>Request lifecycle</b> — see the interactive version in <a href="#request-and-event-flow">Request and Event Flow</a></sub>

<br/><br/>

<img src="docs/images/event-flow.png" alt="Kafka event processing flow sequence diagram" width="820"/>
<br/><sub><b>Event processing flow</b> — batch ingestion, Kafka publish, dead-letter fallback, idempotent consumption</sub>

</div>

---

## Overview

Customer360 Platform is a backend system that ingests customer and transaction data, builds a unified "Customer 360" profile per customer, and exposes it through a versioned, secured, observable FastAPI service. It's built to look and behave like an internal enterprise service rather than a demo script: structured logging, audit trails, rate limiting, a strict Content-Security-Policy, database migrations, an event-driven ingestion path with retry and dead-lettering semantics, and infrastructure-as-code for both Kubernetes and AWS.

The read path is simple by design — `GET /customers` and `GET /customers/{id}` — so the project's depth lives in *how* that data gets there and *how* the service is operated: a pandas-based batch pipeline that cleans raw CSVs into a "gold" dataset, a repository layer that bulk-upserts it into PostgreSQL, a Kafka producer that publishes a domain event per profile, an idempotent Kafka consumer, and a separately implemented transactional outbox module with exponential backoff and dead-lettering.

## Why This Project

This repository exists to demonstrate how I approach backend and platform engineering when the goal is production quality, not just a working demo:

- **API design** — versioned routes, typed Pydantic models, explicit error responses, and machine-readable OpenAPI docs.
- **Data engineering** — a batch cleaning/transformation pipeline feeding a relational store, plus an event-driven path for downstream consumers.
- **Reliability engineering** — retries, exponential backoff, dead-letter handling, and idempotent consumption instead of "happy path only" code.
- **Security engineering** — a strict CSP with no `unsafe-inline` anywhere (including on self-hosted Swagger/ReDoc docs, which is a genuinely fiddly problem — see [Engineering Decisions](#engineering-decisions)), API-key auth, rate limiting, and hardened HTTP headers.
- **Operability** — structured JSON logs, per-request audit logging, health/readiness endpoints, and containerized/orchestrated deployment artifacts.
- **Delivery discipline** — CI that runs lint, strict type checking, tests against real PostgreSQL and Kafka services, Terraform validation, and a Docker build on every push.

## Key Features

### API & Backend

- FastAPI application with Pydantic request/response models and OpenAPI 3.1 schema generation
- API versioning: every resource route is served at both an unversioned path and under `/api/v1`
- Repository pattern (`Customer360Repository`) isolating SQLAlchemy access from route handlers
- Self-hosted Swagger UI and ReDoc — no external CDN dependency, compatible with a strict CSP

### Data & Messaging

- Pandas-based batch ingestion pipeline: raw CSV → validation/cleaning → merged "gold" Customer 360 dataset
- Bulk upsert into PostgreSQL via `INSERT ... ON CONFLICT DO UPDATE`
- Kafka producer publishing a `CustomerEvent` per loaded profile, with idempotent producer settings (`enable.idempotence`, `acks=all`)
- Kafka consumer with in-process idempotent de-duplication by event ID and manual offset commits (at-least-once delivery)
- A separate, fully tested transactional outbox module (table, repository, publisher) implementing exponential backoff and dead-lettering — see [Limitations](#limitations) for its current integration status

### Reliability Highlights

- Producer-side dead-letter redirect (`<topic>.dlq`) on publish failure
- Outbox-side exponential backoff (`2^retry_count` seconds) with a configurable max-retry count before dead-lettering
- `/health` (liveness) and `/ready` (readiness, verifies a live DB connection) endpoints
- Kubernetes liveness/readiness probes and an HPA wired to those same endpoints

### Security Highlights

- API-key authentication (`X-API-Key`) on customer data endpoints
- Per-route rate limiting via SlowAPI (`60/minute` list, `120/minute` detail), with `429` responses
- Strict `Content-Security-Policy` (`default-src 'self'`, `script-src 'self'`, per-request nonce on `style-src`) with **no `unsafe-inline`**
- Hardened response headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`
- Explicit CORS allow-list (no wildcard origins)
- Path parameter validation (length + character allow-list) rejecting malformed customer IDs before they hit the database

### Observability Highlights

- Structured JSON logging for every log line (custom `JsonFormatter`)
- Audit logging middleware recording method, path, status, latency, client IP, and a request ID (`X-Request-ID`, generated or propagated) for every HTTP request
- Prometheus `Counter`/`Histogram` metric definitions in `customer360/metrics/prometheus.py` (see [Limitations](#limitations) — not yet wired to a `/metrics` endpoint)

### DevOps & Infrastructure

- Multi-stage-ready `Dockerfile` and a `docker-compose.yml` for local PostgreSQL + Kafka
- Kubernetes manifests: `Deployment`, `Service`, `ConfigMap`, `Secret`, `HorizontalPodAutoscaler` — hardened with a non-root, read-only-filesystem `securityContext`
- Terraform modules for AWS (VPC/network, RDS PostgreSQL, S3, IAM) validated in CI
- GitHub Actions CI: lint, strict mypy, tests against real Postgres + Kafka service containers, Terraform `fmt`/`validate`, and a Docker build
- Alembic migrations tracking both the profile table and the outbox table
- Live deployment on Railway

## Architecture

The system is organized into four layers:

1. **API layer** (`customer360/api/`) — the FastAPI app, middleware stack (CORS, security headers, audit logging), rate limiting, API-key auth, and the self-hosted docs routes.

   *Why it matters:* every cross-cutting concern (who can call this, how fast, what gets logged) lives in one composable middleware stack instead of being scattered across route handlers — new endpoints inherit security and observability for free.

2. **Infrastructure layer** (`customer360/infrastructure/`) — the SQLAlchemy model, session/engine setup, and the repository that mediates all database access.

   *Why it matters:* route handlers never see a SQL session directly. Query logic, error handling, and logging are centralized in one testable place, so a schema or database change touches one layer, not every endpoint.

3. **Data & messaging layer** (`customer360/ingestion/`, `customer360/spark/`, `customer360/messaging/`, `customer360/outbox/`) — the batch cleaning pipeline, the Customer 360 merge step, the Kafka producer/consumer, and the outbox pattern implementation.

   *Why it matters:* ingestion, transformation, and event publishing are independent, individually testable components rather than one monolithic script — each has its own failure mode (bad input, a down broker) handled where it happens.

4. **Delivery layer** — Docker for containerization, Kubernetes manifests for orchestration, Terraform for AWS infrastructure, and GitHub Actions for CI. Railway builds and runs the container for the public demo.

   *Why it matters:* the same container image is the unit of deployment everywhere — locally, in CI, and on Railway — so "it works on my machine" isn't a category of bug this project has.

> Note: the `customer360/spark/` module is a pandas-based transformation pipeline, not Apache Spark/PySpark — the directory name reflects its role in the data pipeline (the "bronze → gold" merge step), not the underlying engine.

## Architecture Diagram

```mermaid
flowchart TB
    Browser["Browser / API client"]

    subgraph Railway["Railway — live deployment"]
        API["FastAPI app\ncustomer360.api.main"]
        MW["Middleware: CORS, security headers,\naudit logging, rate limiting, API key"]
        Docs["Self-hosted /docs, /redoc\nstrict CSP + per-request nonce"]
    end

    subgraph DB["PostgreSQL"]
        Profiles[("customer360_profiles")]
        OutboxTbl[("outbox_events")]
    end

    subgraph Batch["Batch pipeline (pandas)"]
        Raw[("Raw CSVs")]
        Clean["Clean & validate"]
        Gold[("customer360_gold.csv")]
        Loader["Bulk loader\nload_customer360.py"]
    end

    subgraph Kafka["Kafka"]
        Topic{{"customer360.customer-events.v1"}}
        DLQ{{"...v1.dlq"}}
    end

    Consumer["Idempotent consumer\n(dedupe by event_id)"]
    Outbox["Outbox publisher\n(backoff + dead-letter)"]

    Browser -->|HTTPS| API
    API --> MW
    API --> Docs
    API -->|SQLAlchemy repository| Profiles

    Raw --> Clean --> Gold --> Loader
    Loader -->|bulk upsert| Profiles
    Loader -->|publish CustomerEvent| Topic
    Loader -.on publish failure.-> DLQ

    Topic --> Consumer
    OutboxTbl -.polled by.-> Outbox
    Outbox -.publish.-> Topic

    classDef notLive stroke-dasharray: 5 5
    class Outbox,OutboxTbl notLive
```

*Dashed elements (outbox publisher and table) are implemented and unit-tested but not currently invoked from the live request or ingestion path — see [Limitations](#limitations).*

## Request and Event Flow

**Synchronous read request:**

```mermaid
sequenceDiagram
    participant C as Client
    participant MW as Middleware
    participant R as Route Handler
    participant Repo as Repository
    participant DB as PostgreSQL

    C->>MW: GET /api/v1/customers (X-API-Key)
    MW->>MW: CORS check, security headers, rate limit, API key verification
    MW->>R: forward request
    R->>Repo: list_all()
    Repo->>DB: SELECT ... ORDER BY total_spend DESC
    DB-->>Repo: rows
    Repo-->>R: Customer360Profile[]
    R-->>MW: 200 + JSON
    MW-->>C: response + X-Request-ID, CSP, security headers
```

**Batch ingestion → event publish:**

```mermaid
sequenceDiagram
    participant Job as load_customer360.py
    participant Repo as Customer360Repository
    participant DB as PostgreSQL
    participant P as CustomerEventProducer
    participant K as Kafka topic
    participant DLQ as Kafka DLQ topic
    participant Con as CustomerEventConsumer

    Job->>Repo: bulk_upsert(profiles)
    Repo->>DB: INSERT ... ON CONFLICT DO UPDATE
    Job->>P: publish(CustomerEvent) per profile
    alt publish succeeds
        P->>K: produce(event)
    else Kafka publish fails
        P->>DLQ: republish to <topic>.dlq
    end
    K->>Con: poll()
    Con->>Con: skip if event_id already processed
    Con->>Con: process event
    Con->>K: commit offset
```

## Technology Stack

| Layer | Technology |
| --- | --- |
| API framework | FastAPI, Uvicorn |
| Validation / schemas | Pydantic v2 |
| ORM / database access | SQLAlchemy 2.0 (typed `Mapped` columns) |
| Database | PostgreSQL (production/CI), SQLite (local default fallback) |
| Migrations | Alembic |
| Messaging | Apache Kafka via `confluent-kafka` |
| Rate limiting | SlowAPI |
| Metrics | `prometheus-client` (definitions only — see [Limitations](#limitations)) |
| Batch data processing | pandas |
| Dashboard charts | Chart.js (vendored locally, no CDN — see [Pipeline Monitor](#pipeline-monitor)) |
| Testing | pytest, pytest-cov, FastAPI `TestClient`, Node.js (pure frontend logic in `/demo` and `/demo/pipeline`) |
| Lint / formatting | Ruff |
| Type checking | mypy (strict mode) |
| Containerization | Docker |
| Orchestration | Kubernetes manifests (Deployment, Service, HPA, ConfigMap, Secret) |
| Infrastructure as Code | Terraform (VPC, RDS, S3, IAM modules for AWS) |
| CI/CD | GitHub Actions |
| Live hosting | Railway |

## API Endpoints

All customer-data endpoints are exposed twice: once unversioned (for the live docs/demo) and once under `/api/v1`, so the same handler is reachable at both paths.

| Method | Path | Auth | Rate limit | Description |
| :---: | --- | :---: | :---: | --- |
| `GET` | `/` | none | — | Application status |
| `GET` | `/health`, `/api/v1/health` | none | — | Liveness check |
| `GET` | `/ready`, `/api/v1/ready` | none | — | Readiness check (verifies DB connectivity) |
| `GET` | `/customers`, `/api/v1/customers` | `X-API-Key` | 60/min | List customer profiles |
| `GET` | `/customers/{customer_id}`, `/api/v1/customers/{customer_id}` | `X-API-Key` | 120/min | Get a single customer profile |
| `GET` | `/docs` | none | — | Self-hosted Swagger UI |
| `GET` | `/redoc` | none | — | Self-hosted ReDoc |
| `GET` | `/openapi.json` | none | — | OpenAPI 3.1 schema |
| `GET` | `/demo` | none | — | Demo dashboard HTML page (see [Demo Dashboard](#demo-dashboard)) |
| `GET` | `/demo/api/summary` | none | 60/min | Demo-only summary counts |
| `GET` | `/demo/api/customers` | none | 60/min | Demo-only customer list (same data/serialization as `/customers`, no key required) |
| `GET` | `/demo/api/customers/{customer_id}` | none | 120/min | Demo-only single customer |
| `GET` | `/demo/pipeline` | none | — | Pipeline monitor HTML page (see [Pipeline Monitor](#pipeline-monitor)) |
| `GET` | `/demo/api/pipeline/summary` | none | 60/min | KPIs + pipeline stage counts/health |
| `GET` | `/demo/api/pipeline/events` | none | 60/min | Simulated event stream |
| `GET` | `/demo/api/pipeline/services` | none | 30/min | Service health cards |
| `GET` | `/demo/api/pipeline/charts` | none | 30/min | Chart series |
| `GET` | `/demo/api/pipeline/customer/{customer_id}` | none | 120/min | Per-customer event-flow timeline |
| `GET` | `/workspace` | none | — | Customer360 Cloud Workspace shell HTML page (see [Customer360 Cloud Workspace](#customer360-cloud-workspace)) |
| `PATCH` | `/demo/api/customers/{customer_id}` | none | 20/min | Updates a customer's name/email/city/state, records a real outbox event, and returns the resulting event trace |
| `GET` | `/demo/api/pipeline/history` | none | 60/min | Most-recent-first list of every event (Control Center actions and real customer edits) with its full per-stage trace — backs Event Center, Audit Logs, and the Customers timeline |

The `/demo/api/*`, `/demo/api/pipeline/*`, and `/workspace` routes are excluded from the OpenAPI schema — they exist to support the `/demo`, `/demo/pipeline`, and `/workspace` pages, not as part of the documented, versioned product API.

The authenticated, versioned surface (`/customers`, `/api/v1/customers*`) is still **read-only** — profile creation/updates there happen through the batch ingestion pipeline, not a write endpoint. The one exception is the Customer360 Cloud Workspace's own `PATCH /demo/api/customers/{customer_id}` above, scoped to the same unauthenticated, seeded/fictional demo dataset the rest of `/demo/api/*` already serves (see [Limitations](#limitations)).

## Data Model

**`customer360_profiles`** — the unified customer record served by the API:

| Column | Type | Notes |
| --- | --- | --- |
| `customer_id` | `String(100)` | Primary key |
| `first_name`, `last_name` | `String(100)` | |
| `email` | `String(255)` | Unique, indexed |
| `city`, `state` | `String(100)`, nullable | |
| `transaction_count` | `Integer` | Default `0` |
| `total_spend` | `Float` | Default `0.0` |
| `average_transaction_value` | `Float` | Default `0.0` |
| `created_at`, `updated_at` | `DateTime` | `updated_at` auto-updates on write |

**`outbox_events`** — outbox pattern table (see [Limitations](#limitations) for integration status):

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `Integer` | Primary key, autoincrement |
| `event_id` | `String(36)` | Unique, indexed |
| `event_type` | `String(100)` | |
| `payload` | `Text` | Serialized event JSON |
| `status` | `String(20)` | `PENDING` / `PUBLISHED` / `FAILED` |
| `retry_count` / `max_retries` | `Integer` | Default `0` / `5` |
| `dead_lettered` | `Boolean` | Set once `retry_count >= max_retries` |
| `next_retry_at` | `DateTime`, nullable | Exponential backoff schedule |
| `created_at` / `published_at` | `DateTime` | |

## Reliability Patterns

| Pattern | Where | Behavior |
| --- | --- | --- |
| Transactional outbox | `customer360/outbox/` | Events are written to a DB table with retry accounting; a publisher polls `PENDING` rows and marks them `PUBLISHED` or reschedules them |
| Exponential backoff | `OutboxRepository.increment_retry` | Next retry scheduled at `now + 2^retry_count` seconds |
| Dead-letter queue (producer) | `CustomerEventProducer.publish` | On Kafka publish failure, the event is republished to `<topic>.dlq` |
| Dead-letter queue (outbox) | `OutboxRepository.increment_retry` | Row is flagged `dead_lettered=True`, `status="FAILED"` after `max_retries` |
| Idempotent consumption | `CustomerEventConsumer.consume` | Tracks processed `event_id`s in-process and skips duplicates before committing offsets |
| Idempotent producer | `CustomerEventProducer.__init__` | `enable.idempotence=True`, `acks=all` |
| Idempotent writes | `Customer360Repository.bulk_upsert` | `INSERT ... ON CONFLICT DO UPDATE` keyed on `customer_id` |
| Liveness / readiness | `/health`, `/ready` | `/ready` performs a real `SELECT 1` against the configured database |

## Security

- **Strict Content-Security-Policy** — `default-src 'self'; script-src 'self'; style-src 'self' 'nonce-<per-request>'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`. No `unsafe-inline` or `unsafe-eval` anywhere, including on the documentation pages.
- **Self-hosted API docs** — Swagger UI and ReDoc assets are vendored under `customer360/api/static/` and served from the app itself; nothing is loaded from a third-party CDN. ReDoc renders via `styled-components`, which injects `<style>` tags at runtime — since Chrome only honors a nonce set through an element's `.nonce` property (not `setAttribute`), a small bootstrap script patches `document.createElement` before the ReDoc bundle loads so every dynamically created style tag carries the correct per-request nonce.
- **API-key authentication** — `X-API-Key` header, checked via a FastAPI dependency; missing server-side configuration fails closed with `503` rather than silently allowing access.
- **Rate limiting** — SlowAPI, per-route limits, `429 Too Many Requests` with `X-RateLimit-*` and `Retry-After` headers exposed via CORS.
- **CORS** — explicit origin allow-list (`CORS_ALLOWED_ORIGINS`), `GET`-only, no wildcard.
- **Security headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Strict-Transport-Security`.
- **Input validation** — customer IDs are constrained by length and an explicit character allow-list at the route layer, rejecting malformed input before it reaches a query.

## Observability

- **Structured JSON logging** — every log record is emitted as a single JSON line (timestamp, level, logger, message, plus any structured `extra` fields) via a custom `JsonFormatter`.
- **Audit logging middleware** — every HTTP request logs method, path, status code, duration, client IP, and a request ID; the same ID is echoed back as `X-Request-ID`.
- **Health/readiness endpoints** — `/health` for liveness, `/ready` for a real database connectivity check, both wired into the Kubernetes probes.
- **Metrics (partial)** — `Counter`/`Histogram` definitions exist in `customer360/metrics/prometheus.py`, but they are not yet incremented by the request path and there is no `/metrics` endpoint exposed. Treat this as scaffolding, not a working Prometheus integration — see [Roadmap](#roadmap).

## Testing and Code Quality

- **68 tests** across 12 files (`pytest`), covering the API (auth, rate limiting, CORS, docs/CSP, validation), the repository layer, bulk upsert, the batch loader, Kafka producer/consumer/schemas, and the outbox repository/publisher.
- An `integration`-marked test performs a real Kafka publish/consume round trip; CI runs it against a live Kafka service container (no mocking).
- **Ruff** for linting (`E`, `F`, `I`, `UP`, `B` rule sets).
- **mypy --strict** for type checking.
- **CI** (`.github/workflows/tests.yml`) runs, on every push/PR: Ruff, strict mypy, the full test suite against real PostgreSQL + Kafka service containers, Alembic migrations, `terraform fmt`/`validate`, and a Docker build.

```bash
python -m pytest --cov=customer360 --cov-report=term-missing
python -m ruff check .
python -m mypy customer360
```

## Local Development

```bash
git clone https://github.com/pbolla1311/customer360-platform.git
cd customer360-platform

python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"

cp .env.example .env

uvicorn customer360.api.main:app --reload
```

The app defaults to a local SQLite file (`customer360.db`) when `DATABASE_URL` is unset, so the API and its tests run without any external services. Kafka-dependent code (the producer, consumer, and the batch loader's event publishing step) has no offline fallback — it needs a reachable broker (`KAFKA_BOOTSTRAP_SERVERS`, default `localhost:9092`). For PostgreSQL/Kafka parity with CI and production, use the Docker Compose stack below.

## Docker Setup

`docker-compose.yml` provisions local PostgreSQL and Kafka (the application itself runs on the host, pointed at them via `.env`):

```bash
docker compose up -d      # or: make up
docker compose ps
docker compose logs -f    # or: make logs
docker compose down       # or: make down
```

To build and run the API itself in a container:

```bash
docker build -t customer360-platform .
docker run --rm -p 8000:8000 --env-file .env customer360-platform
```

## Database Migrations

```bash
python -m alembic upgrade head        # apply all migrations
python -m alembic history             # view the revision chain
python -m alembic revision --autogenerate -m "description"
```

Current revision chain:

1. `b8584a766c1f` — create `customer360_profiles` table
2. `12c285050662` — add `outbox_events` table
3. `f45862c54dbc` — add retry and dead-letter-queue fields
4. `1811e890ede7` — add `next_retry_at` timestamp

## Kubernetes Deployment

Manifests live under [`k8s/`](k8s/): `deployment.yaml`, `service.yaml`, `configmap.yaml`, `secret.yaml`, and `hpa.yaml`. The Deployment runs as non-root with a read-only root filesystem and no extra Linux capabilities, wires `/health`/`/ready` into liveness/readiness probes, and the HPA scales 2–6 replicas on 70% CPU utilization.

**These manifests are included in the repository and are not currently applied to a live cluster.** To try them against your own cluster:

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml        # replace placeholder values first
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

## Terraform Infrastructure

Terraform modules under [`terraform/`](terraform/) define AWS infrastructure: a VPC with public/private subnets (`modules/network`), an RDS PostgreSQL instance (`modules/rds`), an S3 bucket (`modules/s3`), and an application IAM role (`modules/iam`).

**This infrastructure is `terraform validate`-checked in CI on every push; it is not continuously applied, and the GitHub Actions workflow that would build/publish a container to AWS is currently disabled** (`.github/workflows-disabled/cd.yml`). To provision it yourself:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in your own values
terraform init
terraform plan
terraform apply
```

## Railway Deployment

**Railway hosts the public live demo** linked at the top of this README. Railway builds the repository's `Dockerfile` directly and runs `uvicorn customer360.api.main:app`; pushes to `main` trigger an automatic redeploy. This is the only environment where the application is actually running continuously — the Kubernetes and Terraform/AWS paths are implemented and validated but not live (see above).

## Project Structure

```text
customer360-platform/
├── customer360/
│   ├── api/                # FastAPI app, middleware, security, self-hosted docs
│   │   └── static/         # Vendored Swagger UI / ReDoc assets
│   ├── infrastructure/     # SQLAlchemy models, session, repository, bulk loader
│   ├── ingestion/          # Raw CSV cleaning/validation
│   ├── spark/              # Pandas-based Bronze→Gold transformation
│   ├── messaging/          # Kafka producer, consumer, event schemas, settings
│   ├── outbox/             # Transactional outbox model, repository, publisher
│   ├── metrics/            # Prometheus metric definitions
│   ├── config.py           # Environment-driven configuration
│   └── logging_config.py   # Structured JSON logging setup
├── alembic/                # Database migrations
├── k8s/                    # Kubernetes manifests
├── terraform/              # AWS infrastructure modules
├── tests/                  # pytest suite (unit + integration)
├── docker-compose.yml      # Local PostgreSQL + Kafka
├── Dockerfile
├── DEPLOYMENT.md
└── .github/
    ├── workflows/tests.yml           # CI: lint, types, tests, terraform, docker build
    └── workflows-disabled/cd.yml     # AWS/ECR publish workflow (currently disabled)
```

## Example API Requests

Against the live Railway deployment:

```bash
# Application status
curl https://customer360-platform-production.up.railway.app/

# Liveness
curl https://customer360-platform-production.up.railway.app/health

# Readiness (checks the database connection)
curl https://customer360-platform-production.up.railway.app/ready

# OpenAPI schema
curl https://customer360-platform-production.up.railway.app/openapi.json

# List customers (requires X-API-Key; the live demo has no API_KEY configured,
# so this currently returns 503 "API security is not configured" rather than
# data — see the note in Live Demo above)
curl -H "X-API-Key: <YOUR_API_KEY>" \
  https://customer360-platform-production.up.railway.app/customers

# Get a single customer profile
curl -H "X-API-Key: <YOUR_API_KEY>" \
  https://customer360-platform-production.up.railway.app/customers/CUST00001
```

Against a local instance (with `API_KEY` set, e.g. via `.env`):

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/customers
```

## Engineering Decisions

- **Repository pattern over inline SQLAlchemy queries.** Route handlers depend on `Customer360Repository`, not the ORM session directly, so query logic, error handling, and logging are centralized and independently testable.
- **Read/write split between the API and the batch pipeline.** The HTTP API is intentionally read-only; profile data is produced by the batch loader. This keeps the request path simple and pushes bulk-write concerns (batching, upsert semantics) into a component designed for them.
- **Two retry/DLQ strategies, on purpose.** The Kafka producer's immediate DLQ redirect handles hard publish failures; the outbox module's exponential backoff models a slower, more patient retry policy for a durable, at-least-once delivery guarantee. They're implemented as separate, independently tested components rather than conflated into one.
- **Strict CSP with no exceptions, even for vendor JS.** Rather than adding `unsafe-inline` to make Swagger UI/ReDoc work, both toolchains' bootstrap code was moved into external scripts, and ReDoc's runtime style injection was solved with a `document.createElement` patch plus a per-request nonce — keeping `script-src`/`style-src` genuinely strict instead of relaxing the policy to fit the tooling.
- **API versioning without route duplication logic.** Each resource is registered once per path (unversioned and `/api/v1`) using the same handler function, so there's a single source of truth for behavior while still exposing a versioned contract.
- **SQLite as the zero-config local default.** `DATABASE_URL` falls back to a local SQLite file so the API and most of the test suite run without Docker; PostgreSQL is used in CI and production to catch dialect-specific issues (e.g., `INSERT ... ON CONFLICT`) before they ship.

## Limitations

Being direct about the current gaps:

- **The authenticated, versioned API is read-only.** There are no `POST`/`PUT`/`DELETE` endpoints under `/customers`/`/api/v1/*`; writes there happen only through the batch pipeline. The Workspace's `PATCH /demo/api/customers/{customer_id}` is the one write endpoint in the app, deliberately scoped to the same unauthenticated, seeded/fictional demo dataset as the rest of `/demo/api/*` — see [Customer360 Cloud Workspace](#customer360-cloud-workspace).
- **The outbox pattern is implemented and tested but not wired in.** `OutboxRepository`/`OutboxPublisher` are exercised by their own test suite and have a migrated table, but nothing in the live ingestion path currently writes to or drains that table — the batch loader publishes to Kafka directly.
- **No standalone Kafka consumer process is deployed.** `CustomerEventConsumer` is implemented and covered by a real broker round-trip integration test, but there's no long-running worker (Kubernetes Deployment, entrypoint script, etc.) that runs it continuously.
- **Idempotent de-duplication is in-process only.** The consumer's processed-event tracking is an in-memory set; it resets on restart and isn't shared across consumer instances.
- **Prometheus metrics aren't exposed.** The `Counter`/`Histogram` objects exist but aren't incremented by request handling, and there is no `/metrics` endpoint.
- **The `spark/` module uses pandas, not Apache Spark.** No PySpark dependency is installed; the module name reflects its role in a Bronze→Gold pipeline, not the execution engine.
- **`dbt/models/` and `airflow/dags/` are empty placeholders**, as are the top-level `ingestion/`, `quality/`, `infrastructure/`, `diagrams/`, and `demo/` directories. (The top-level `scripts/` directory now holds `seed_demo_customers.py` — see [Demo Dashboard](#demo-dashboard) — but is otherwise still a placeholder for future operational scripts.)
- **No Streamlit dashboard exists**, despite `streamlit` being listed as a dependency and `apps/dashboard/` existing as an empty directory.
- **AWS deployment is not live.** Terraform is validated in CI and Kubernetes manifests are included, but the workflow that would publish a container to AWS is disabled; Railway is the only environment actually running the app.
- **Single static API key**, not per-client keys, OAuth, or user accounts.
- **`/demo/pipeline`'s Kafka/consumer/outbox telemetry is simulated, not scraped from a live broker.** It's a direct, honest consequence of the two gaps above (no deployed consumer worker, outbox not wired in) — see [Pipeline Monitor](#pipeline-monitor) for exactly which numbers on that page are real vs. simulated, and why.
- **The Pipeline Control Center's state is global, not per-visitor.** `PipelineSimulationEngine` is one process-wide singleton — if two people have `/demo/pipeline` (or the Workspace's Pipeline tab) open at once, one clicking "Reset Demo" clears what the other is looking at, and a customer edit one visitor makes shows up in every other visitor's Event Center/Audit Logs too. This is a deliberate reading of the task's own "single source of truth" requirement (matching a real shared ops dashboard), not an oversight; a per-session engine keyed by a cookie/token would be the fix if this ever needs to support concurrent independent demos.
- **The Workspace's Overview/Monitoring throughput and KPI numbers are still `pipeline_telemetry.py`'s ambient, time-seeded simulation**, same as the standalone Pipeline Monitor — a real customer edit is reflected precisely as its own event/trace/timeline entry, but it doesn't change the ambient messages-processed/throughput baseline those views also show.

## Roadmap

- Wire the outbox publisher into the batch/write path and run it on a schedule
- Deploy `CustomerEventConsumer` as a standalone worker with a persisted (not in-memory) idempotency store — this, plus the outbox item above, is what would let `/demo/pipeline` show real Kafka/retry/DLQ telemetry instead of simulated
- Increment the existing Prometheus metrics from request middleware and expose `/metrics`
- Extend the Workspace's write path (`PATCH /demo/api/customers/{customer_id}`) to the authenticated `/api/v1` surface, backed by the outbox pattern for at-least-once event delivery
- Re-enable the AWS CD workflow and deploy the Terraform-defined infrastructure
- Build the Streamlit dashboard the `apps/dashboard/` and `docs/ARCHITECTURE.md` already scope out
- Replace the pandas transformation step with real PySpark, and add the dbt models/Airflow DAGs the project layout reserves space for
- Move from a single static API key to per-client credentials

## Resume / Interview Summary

Designed and built a production-style customer data platform end to end: a versioned FastAPI service backed by PostgreSQL and SQLAlchemy, an event-driven ingestion path using Kafka with idempotent producers/consumers and a transactional-outbox retry/dead-letter design, and a security posture built around a strict Content-Security-Policy (self-hosted API docs, no `unsafe-inline` anywhere) plus API-key auth and rate limiting. Delivered with Alembic migrations, structured JSON logging and audit trails, a GitHub Actions pipeline that runs strict type checking and tests against real PostgreSQL/Kafka service containers, Docker/Kubernetes/Terraform artifacts for containerized and cloud deployment, and a live deployment on Railway.

### Highlights

- Diagnosed and fixed a real browser-level CSP bug (ReDoc's runtime `styled-components` style injection) by patching `document.createElement` with a per-request cryptographic nonce — verified against a real headless Chrome session, not just static assertions.
- Implemented two independent retry/dead-letter strategies (producer-level immediate DLQ redirect, outbox-level exponential backoff) and covered both with unit tests plus a live Kafka round-trip integration test run in CI.
- Kept infrastructure honest: Kubernetes and Terraform are implemented and validated in CI, clearly documented as not continuously deployed, rather than overstated as "in production."

## Author

**Prakhyath Bolla**
GitHub: [@pbolla1311](https://github.com/pbolla1311)
Repository: [github.com/pbolla1311/customer360-platform](https://github.com/pbolla1311/customer360-platform)
