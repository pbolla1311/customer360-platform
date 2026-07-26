# README Screenshots

Tracks the visual assets under `docs/images/` used by `README.md`, and what's
still outstanding.

When a screenshot is captured, save it under `docs/images/` using the
filename below, embed it in the relevant `README.md` section, and check it
off here.

## Checklist

- [x] **Social preview** — `social-preview.png`
  Dark-theme hero banner (title, tagline, tech stack icons, minimal
  architecture illustration). Generated from an HTML/CSS template rendered
  with headless Chrome, not a live screenshot.

- [x] **Architecture diagram (exported)** — `architecture.png`
  Branded PNG export of the Mermaid architecture diagram in `README.md`
  (`## Architecture Diagram`), rendered with `@mermaid-js/mermaid-cli` on a
  custom dark theme and composited onto a title/footer card.

- [x] **Request flow (exported)** — `request-flow.png`
  Same treatment as above, for the "Synchronous read request" sequence
  diagram in `## Request and Event Flow`.

- [x] **Event flow (exported)** — `event-flow.png`
  Same treatment as above, for the "Batch ingestion → event publish"
  sequence diagram in `## Request and Event Flow`.

- [x] **Swagger UI** — `swagger-ui.png`
  Real screenshot of `/docs` on the live Railway deployment.

- [x] **ReDoc** — `redoc.png`
  Real screenshot of `/redoc` on the live Railway deployment.

- [ ] **Railway active deployment** — `railway-deployment.png`
  Screenshot of the Railway dashboard showing the `customer360-platform`
  service in a successful/active deployment state. Requires access to the
  Railway project dashboard (not captured by an automated agent working only
  from the repo and public URLs).

- [ ] **GitHub Actions passing** — `github-actions-passing.png`
  Screenshot of a green run of the `CI` workflow
  (`.github/workflows/tests.yml`) in the GitHub Actions tab, showing the
  `quality`, `test`, `terraform`, and `container` jobs all passing.

## Notes

- The three exported diagrams (`architecture.png`, `request-flow.png`,
  `event-flow.png`) are generated, not hand-drawn — their Mermaid source
  lives inline in `README.md` and should stay the source of truth. If a
  diagram's Mermaid source changes, regenerate the matching PNG so they
  don't drift apart.
- All PNGs are palette-quantized (`sharp`, `png({ palette: true })`) to keep
  file sizes small for a fast-loading README; re-optimize after regenerating
  rather than committing a raw multi-MB screenshot.
- Redact or crop out any local environment details (file paths, local IPs)
  before committing new screenshots.
