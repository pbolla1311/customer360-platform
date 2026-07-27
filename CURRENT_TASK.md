# Current Task

## Task: Build Enterprise Pipeline Monitoring Dashboard (v1.1 follow-on)

**Status:** Complete
**Started / Completed:** 2026-07-27

### What shipped

A flagship `/demo/pipeline` page (Datadog/Confluent-Cloud-style) that
demonstrates the platform's Kafka/outbox/retry/DLQ architecture: 8 animated
KPI cards, an animated 7-stage pipeline visualization, a live-scrolling
event stream, 6 Chart.js charts, 6 service health cards, and a per-customer
illustrative event-flow timeline. No existing route, auth, or test changed
behavior — only additions.

### Two decisions made without re-asking (extending the v1.1 `/demo` precedent)

1. **Chart.js vendored locally** — `customer360/api/static/demo/vendor/chart.umd.min.js`
   (4.5.1, MIT), same pattern as the pre-existing vendored
   `swagger-ui-bundle.js`/`redoc.standalone.js`. Satisfies "use Chart.js or
   ECharts" while keeping `script-src 'self'`, no CDN, no `unsafe-eval`.
2. **Real data stays real; everything with no live backing is a labeled,
   deterministic simulation**, not random noise and not fabricated. See
   README → Pipeline Monitor for the exact real/simulated table. In short:
   real = `PostgreSQL` stage, `Database`/`API` service cards, real
   `outbox_events` count if any exist, a selected customer's real
   `created_at`. Simulated = the other 6 stages, `Kafka`/`Consumer`/`Outbox`/
   `Scheduler` service cards, all 8 KPIs except what's listed above, the
   event stream, and all 6 charts.

### Files changed/added

- `customer360/api/pipeline_telemetry.py` — pure, deterministic simulation
  engine (23 unit tests, no FastAPI/DB/Kafka needed).
- `customer360/api/main.py` — `/demo/pipeline` + 5 `/demo/api/pipeline/*`
  routes, a briefly-cached `_real_pipeline_inputs()` helper.
- `customer360/infrastructure/repository.py` — added `count_all()` and
  `list_customer_ids()` (efficient, single-purpose queries; avoids
  over-fetching full rows just to count/sample IDs).
- `customer360/api/static/demo/pipeline/{index.html,pipeline.css,pipeline.js}`,
  `customer360/api/static/demo/vendor/chart.umd.min.js` — new.
- Nav updates: `/demo` header, landing page Live Deployment card + footer
  link + a new "Pipeline Monitor" feature card.
- Tests: `tests/api/test_pipeline_telemetry.py` (23),
  `tests/api/test_pipeline_js.py` (11, Node shell-out), ~28 new tests in
  `tests/api/test_main.py` (routes/assets/CSP/empty/error/regression), plus
  2 new repository tests.
- Docs: README "Pipeline Monitor" section + endpoint table + Limitations/
  Roadmap/Tech-Stack updates; `docs/ARCHITECTURE.md` new "Demo & Pipeline
  Monitoring Layer" section; `pyproject.toml` package-data.

### Verified

- `pytest -q`: **183 passed**, 0 failed, 0 skipped (183 = 124 pre-existing at
  the start of this task + 59 new: 23 in `test_pipeline_telemetry.py`, 11 in
  `test_pipeline_js.py`, 22 pipeline-specific in `test_main.py`, 3 in
  `test_repository.py`).
- `ruff check .` clean. `mypy customer360` (matches CI) clean, 0 issues
  across 32 files.
- Wheel build includes the new pipeline/vendor assets (`unzip -l` verified).
- `docker build` succeeds; ran the built image against the real local
  Postgres (via `host.docker.internal`), hit every new endpoint, and
  confirmed the `PostgreSQL` stage exactly matched the real row count (5).
- Playwright (headless Chromium) against a live local server at 1440×900
  and 390×844: zero console errors, zero CSP violations, zero horizontal
  overflow (after one fix — see below), 7 stage nodes, 6 service cards, 6
  charts with actually-painted pixels, working customer-flow select, and
  KPI/count-up values that were non-zero and animated.
- **One real bug found and fixed during browser verification:** `.panel`
  (a CSS grid item) had no `min-width: 0`, so the pipeline visualization's
  internal `overflow-x: auto` scroller wasn't containing its child's
  `min-width: 760px` — it was widening the whole grid item instead, causing
  horizontal page overflow on mobile. Fixed in `pipeline.css`. Also added
  `-webkit-backdrop-filter` for Safari.
- **One real bug found and fixed during test-writing:** the module-level
  cache in `_real_pipeline_inputs()` doesn't know about
  `dependency_overrides`, so tests that swap the DB session need to reset
  it first (documented and added in `test_main.py`) — this is fine in
  production (small staleness window is the intended trade-off) but broke
  test isolation until fixed.

Note on the local dev environment: at the start of this task, `docker-compose`'s
`postgres`/`kafka` containers had exited (unrelated to any code change —
they'd stopped since the last session). This caused the *existing* test
suite to fail before I'd changed anything. Restarted both via
`docker compose up -d postgres kafka` and re-verified 150 pre-existing tests
passed clean before adding anything new.

### Known limitations

- Everything in the "simulated" column of the Pipeline Monitor README table
  will keep looking exactly the same until the outbox pattern is wired in
  and a consumer worker is actually deployed (pre-existing gaps, not
  introduced or hidden by this task — see Roadmap).
- Chart.js's 208KB vendored bundle is the single largest static asset added;
  acceptable for a demo page, but worth knowing if bundle size becomes a
  concern later.
- Screenshot files for the new README checklist weren't captured to
  `docs/images/` (same as the v1.1 task) — left as a checklist.

### Next task after this one

Wire the same Node-based JS tests (`test_demo_js.py`, `test_pipeline_js.py`)
into the CI `quality` job in `.github/workflows/tests.yml`, so a frontend
regression in either dashboard fails CI the same way Ruff/mypy would. Right
now that coverage only runs via local `pytest` (which already shells out to
Node) — CI's `ubuntu-latest` runners have Node preinstalled, so this is
close to a no-op addition, just an explicit step.

---

## Draft release notes (not published)

**Tag:** `v1.2.0`
**Title:** Customer360 Platform v1.2.0
**Theme:** Enterprise Pipeline Monitoring Dashboard

> Adds `/demo/pipeline` — a Datadog/Confluent-Cloud-style monitoring
> dashboard that visualizes the platform's Kafka, outbox-pattern, retry, and
> dead-letter-queue architecture: 8 animated KPI cards, an animated 7-stage
> pipeline flow, a live event stream, 6 charts (Chart.js, vendored locally,
> no CDN), 6 service health cards, and a per-customer event-flow timeline.
>
> - The `PostgreSQL` stage and the `Database`/`API` service cards are real,
>   sourced from the live database; everything else that has no live Kafka
>   broker or consumer worker to back it is a deterministic, clearly
>   labeled simulation — never random, never presented as production
>   telemetry.
> - New unauthenticated `/demo/api/pipeline/*` endpoints, reusing the same
>   repository layer as the real API. `/customers`, `/api/v1/*`, and the
>   v1.1 `/demo/api/*` endpoints are unchanged.
> - No changes to auth, CSP, security headers, Swagger UI, ReDoc, or the
>   OpenAPI schema.
