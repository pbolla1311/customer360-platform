# Customer 360 Platform

A production-style Customer 360 data platform that combines batch and streaming data, creates unified customer profiles, and exposes analytics through APIs and dashboards.

## Planned Architecture

- Batch and streaming ingestion
- Bronze, Silver, and Gold data layers
- Apache Spark and PySpark transformations
- Airflow orchestration
- dbt analytical models
- PostgreSQL warehouse
- FastAPI analytics API
- Streamlit dashboard
- Docker-based local development
- GitHub Actions CI/CD
- Automated testing and data-quality checks

## Current Status

Foundation initialized.

## Local Setup

```bash
cp .env.example .env
docker compose up -d
docker compose psEOF
