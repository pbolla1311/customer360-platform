.PHONY: help up down logs test lint

help:
	@echo "Available commands:"
	@echo "  make up     Start local services"
	@echo "  make down   Stop local services"
	@echo "  make logs   Show service logs"
	@echo "  make test   Run tests"
	@echo "  make lint   Run Ruff"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	python3 -m pytest

lint:
	python3 -m ruff check .
