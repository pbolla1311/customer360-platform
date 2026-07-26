# README Screenshots — To Capture

This file tracks the screenshots we still need to capture and add to
`docs/images/` so the README can embed them. None of these exist yet — this
is a checklist, not an index of current assets.

When a screenshot is captured, save it under `docs/images/` using the
filename below, embed it in the relevant `README.md` section, and check it
off here.

## Checklist

- [ ] **Swagger UI** — `swagger-ui.png`
  Full-page capture of `/docs` on the live Railway deployment, showing the
  endpoint list expanded (root, health, ready, customers).

- [ ] **ReDoc** — `redoc.png`
  Full-page capture of `/redoc` on the live Railway deployment, showing the
  operation list and at least one expanded schema.

- [ ] **Railway active deployment** — `railway-deployment.png`
  Screenshot of the Railway dashboard showing the `customer360-platform`
  service in a successful/active deployment state.

- [ ] **GitHub Actions passing** — `github-actions-passing.png`
  Screenshot of a green run of the `CI` workflow
  (`.github/workflows/tests.yml`) in the GitHub Actions tab, showing the
  `quality`, `test`, `terraform`, and `container` jobs all passing.

- [ ] **Architecture diagram (exported)** — `architecture-diagram.png`
  PNG/SVG export of the Mermaid architecture diagram in `README.md`, for use
  anywhere a rendered image is preferable to inline Mermaid (e.g. a resume
  PDF or a non-GitHub viewer).

## Notes

- Capture at a reasonable width (~1280px) so images stay readable when
  embedded in the README without excessive scrolling.
- Prefer PNG for UI screenshots; SVG (if available) for the exported
  architecture diagram.
- Redact or crop out any local environment details (file paths, local IPs)
  before committing.
