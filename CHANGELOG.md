# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [3.5.0] — Customer360 Cloud: multi-tenant Organizations, Users, Roles & API Keys

### Added

- `organizations`, `users`, `memberships`, `invitations`, `api_keys` tables and a nullable `customer360_profiles.organization_id`, via one Alembic migration (`41276a9b92f6`) that also backfills every pre-existing customer row into a default "Demo Workspace" organization.
- `/login`: pick a seeded user to sign in as (no password/email verification), then a workspace if the user belongs to more than one organization, or create a brand-new organization from scratch.
- Demo-tier session auth via Starlette's `SessionMiddleware` (signed cookie, no server-side store) and a new `customer360/tenancy/` package: `Organization`/`User`/`Membership`/`Invitation`/`ApiKey` models and repositories, plus a fixed 5-role permission matrix (`admin`/`operations`/`customer_success`/`executive`/`viewer`) in `customer360/tenancy/permissions.py`.
- New `/demo/api/*` endpoints: auth (`users`/`login`/`logout`/`session`/`switch-workspace`), organization signup/branding, membership listing/role-change/removal, invitation send/accept/revoke, and API key generate/rotate/revoke/verify.
- Workspace switcher and signed-in user block in the `/workspace` sidebar; nav items hidden per role via a `NAV_PERMISSIONS` map mirrored in JS.
- Settings gained Organization, Users, Invitations, and API Keys tabs (reusing the existing `.ws-tabs` component).
- Event Center and Audit Logs now show Organization and Triggered By; Overview gained Active Users / Organizations / Pending Invitations KPI cards; the Notification Center gained a real "Invitation accepted" type.
- `scripts/seed_demo_tenancy.py`: idempotent, opt-in seeding of demo organizations, users, memberships, and invitations.

### Changed

- `GET /demo/api/customers` and `GET /demo/api/pipeline/history` return organization-scoped results when a session is present, and fall back to their exact pre-v3.5 (unscoped) behavior with no session — verified by dedicated regression tests.
- `PATCH /demo/api/customers/{id}`'s audit trail now records the real signed-in user's name as `actor` (falling back to `"Workspace User"` with no session), and 404s/403s on cross-organization access or insufficient role.
- The Pipeline Control Center's inject-failure/retry/recover/reset actions and all organization-management endpoints now require the `pipeline.operate`/`organization.manage` permission when a session is present; ungated, as before, with no session.

### Scope notes

- Org-scoping is limited to `/workspace` and `/demo/api/*`; `/customers` and `/api/v1/customers*` are unaffected.
- API Keys are real (generated, hashed, rotatable, revocable, verifiable) but do not gate `/api/v1`, which keeps its existing static-key auth.
- "User mentions" and "task assignment" notifications from the original spec were descoped — no underlying data model exists for either; only the real "Invitation accepted" notification was added.

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
