# Contributing

This started as a solo portfolio project, but issues and pull requests are welcome.

## Getting started

1. Fork the repository and clone your fork.
2. Follow [README.md → Local Development](README.md#local-development) to get the app running with a local SQLite database, or [README.md → Docker Setup](README.md#docker-setup) for PostgreSQL/Kafka parity with CI.
3. Create a branch off `main` for your change.

## Before opening a pull request

Run the same checks CI runs:

```bash
python -m pytest --cov=customer360 --cov-report=term-missing
python -m ruff check .
python -m mypy customer360
```

If you touched any of the vanilla-JS frontend under `customer360/api/static/`, also run the Node-backed pure-logic tests:

```bash
python -m pytest tests/api/ -k _js
```

## Guidelines

- Keep changes backward compatible — existing tests should keep passing unmodified unless the change is explicitly a bug fix for behavior those tests pin.
- Prefer extending an existing pattern (repository methods, `window.*Logic` pure-function modules, the shared design system in `customer360/api/static/shared/`) over introducing a new one.
- Be honest about real vs. simulated/illustrative data — see [README.md → Limitations](README.md#limitations) for the convention this project follows.
- Open an issue first for anything larger than a small fix, so we can agree on the approach before you invest time in it.

## Reporting bugs

Open a GitHub issue with steps to reproduce, what you expected, and what actually happened. Include the output of `python -m pytest` if it's a test failure.
