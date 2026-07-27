# Current Task

## Task: Build Customer360 Demo Dashboard v1.1

**Status:** Complete
**Started:** 2026-07-27
**Completed:** 2026-07-27

### What shipped

An interactive, recruiter-facing demo dashboard at `GET /demo`, on top of the
existing FastAPI backend and PostgreSQL database, without touching the
landing page's existing content, Swagger UI, ReDoc, OpenAPI schema, health
endpoints, security headers, CSP, or GitHub stats — only adding to them
(a "Launch Demo" CTA, a Live Deployment card, a footer link).

### Key architecture decision (see README → Demo Dashboard for the full writeup)

`GET /api/v1/customers*` require `X-API-Key`, a real secret that browser JS
can never hold safely, and that secret isn't set on the live Railway
deployment today (confirmed in README's pre-existing "Live Demo" note — those
routes already return `503` there). Resolution (user-approved): new
unauthenticated, read-only routes — `/demo/api/summary`, `/demo/api/customers`,
`/demo/api/customers/{id}` — reuse the same `Customer360Repository` and
`serialize_profile()` as the real endpoints, which are completely unchanged
and still key-gated.

### Files changed/added

- `customer360/api/main.py` — `DemoSummaryResponse` model, `/demo`,
  `/demo/api/summary`, `/demo/api/customers`, `/demo/api/customers/{id}`.
- `customer360/api/static/demo/{index.html,demo.css,demo.js}` — new dashboard.
- `customer360/api/static/site/index.html` — Launch Demo CTA, demo card,
  footer link.
- `scripts/seed_demo_customers.py` (+ `scripts/__init__.py`) — idempotent,
  `ENABLE_DEMO_SEED`-gated seed of 10 fictional customers.
- `tests/api/test_main.py` — demo route/asset/CSP/empty/error/v1-regression
  tests; updated live-deployment-card count and footer assertion.
- `tests/api/test_demo_js.py` — Node shell-out tests for demo.js pure logic.
- `tests/scripts/test_seed_demo_customers.py` — seed dataset/idempotency/gate
  tests.
- `pyproject.toml` — package-data for `api/static/demo/*`.
- `README.md` — Demo Dashboard section, seeding docs, updated API table,
  updated Limitations (scripts/ is no longer an empty placeholder).

### Verified

- `pytest` 124/124 passing (was 83 before this task).
- `ruff check .` clean. `mypy customer360` (matches CI) clean, 0 issues.
- Wheel build includes the new `api/static/demo/*` assets (confirmed via
  `unzip -l`).
- `docker build` succeeds; ran the built image, seeded it, and hit every new
  endpoint plus the untouched `/api/v1/customers` (still 401 without a key,
  200 with one) inside the container.
- Playwright (headless Chromium, installed just for this check) against the
  running container at 1440×900 and 390×844: zero console errors, zero CSP
  violations, zero horizontal overflow, search/clear/select/keyboard-nav all
  functional, empty-state and error-state (mocked 500) both render correctly.

### Known limitations (also in README → v1.1 scope and limitations)

- "Active Profiles" is real but derived (`transaction_count > 0`), not a
  `status` column. "Events Processed" is a labeled sample metric — the API
  exposes no live Kafka event count.
- Activity Timeline is 100% frontend-illustrative, generated from the
  customer ID; not a real events/transactions feed.
- Screenshot files for the README checklist were not captured to disk (the
  Playwright captures live in the session's scratch dir, not `docs/images/`)
  — left as an explicit checklist in the README for whoever adds them.

### Next recommended task

Wire a small CI job that runs the same Node shell-out tests (or at least
`node --check customer360/api/static/demo/demo.js`) inside
`.github/workflows/tests.yml`'s `quality` job, so a future JS regression in
the demo dashboard fails CI the same way a Ruff/mypy regression would —
right now that coverage only runs locally via pytest + Node.
