# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [3.0.0] — Customer360 Cloud: full customer lifecycle & audit trail

### Added

- `status` (`active`/`archived`) and `tags` columns on `customer360_profiles`, via one additive Alembic migration (`fddaf5d4cd64`). Archive/Restore reuse the existing `PATCH /demo/api/customers/{id}` endpoint (`{"status": "archived"}`) rather than a new route.
- Deterministic `correlation_id` (`corr-{event_id}`) on every event response, added as a Pydantic computed field — no changes to the simulation engine.
- A before/after audit trail: `PATCH` responses and `GET /demo/api/pipeline/history` entries now carry an `audit` block (actor, changed fields, before/after values) for real customer edits; Control Center demo actions carry `audit: null`.
- Customer Profile is now a tabbed workspace: Overview, Timeline & Activity, Orders (aggregate, not fabricated per-order rows), Events, Audit, Pipeline Trace. Selecting a customer updates the URL to `#/customers/{customer_id}`.
- Computed, non-persisted **Customer Score** (0–100, derived from spend/frequency/recency), status filter, and client-side pagination on the Customers view.
- Monitoring: Latency Trend and Retry Queue/DLQ Trend charts, plus an honest instantaneous **Service Uptime** snapshot.
- Analytics: Customer Lifetime Value, Active Customers (status- and transaction-aware), and a compact Pipeline Metrics row.
- Overview: Customer Growth sparkline, real derived **Upcoming Tasks** (DLQ/retry-queue/archived-count signals), and **Quick Actions**.
- **Global Search** and a **Notification Center** in the workspace topbar — both pure client-side aggregation over already-fetched data; no new backend endpoints. Unread notifications are tracked via a `localStorage` timestamp.

### Changed

- `GET /demo/api/customers*` responses now include `status` and `tags`.
- The `PATCH /demo/api/customers/{id}` handler's event-type derivation was generalized: a single `changes` list (from a full before/after snapshot) now drives labeling, adding `"Account Archived"` ahead of the existing rules.

## [2.0.0] — Customer360 Cloud Workspace

### Added

- `/workspace`: a single, sidebar-navigated SaaS-style shell (Overview, Customers, Event Center, Pipeline, Monitoring, Analytics, Audit Logs, API Explorer, Settings) unifying the platform into one continuous product experience.
- `PATCH /demo/api/customers/{customer_id}`: a real customer edit that updates `customer360_profiles`, mirrors a real `outbox_events` row, and produces a pipeline trace — labeled `Email Changed`/`Address Changed`/`Customer Updated`.
- `GET /demo/api/pipeline/history`: most-recent-first list of every event (Control Center actions and real customer edits alike) with its full per-stage trace, backing Event Center, Audit Logs, and the Customers timeline.
- `PipelineSimulationEngine.record_customer_update()` and an internal trace-history list, reusing the existing happy-path/outbox-mirroring machinery.
- Landing page CTA changed from "Launch Demo" to "Open Workspace"; `/demo` and `/demo/pipeline` remain live, unchanged, as legacy views.

## [1.2.0] — Pipeline Control Center

### Added

- Interactive Control Center toolbar on `/demo/pipeline`: Generate Customer Event, Replay Last Event, Inject Failure (5 types), Retry Failed Event, Recover Consumer, Reset Demo.
- `PipelineSimulationEngine`: a thread-safe, in-memory singleton providing the cross-request state the passive v1.1 dashboard couldn't. Deterministic retry resolution (no randomness) via a shared `consumer_healthy` lever.
- Best-effort mirroring of Control Center actions into real `outbox_events` rows via the existing `OutboxRepository`.

## [1.1.0] — Pipeline Monitor & Demo Dashboard

### Added

- `/demo`: an interactive, recruiter-facing dashboard over the live Customer360 API — search, select, and view real seeded customer profiles.
- `/demo/pipeline`: an enterprise-monitoring-style dashboard (KPI cards, pipeline flow visualization, live event stream, charts, service health) visualizing the platform's event-driven architecture, with real-vs-simulated data clearly labeled throughout.
- `scripts/seed_demo_customers.py`: idempotent, opt-in seeding of fictional demo customer data.
