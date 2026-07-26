import json
import logging

from fastapi.testclient import TestClient

from customer360.api.main import app
from customer360.logging_config import JsonFormatter

client = TestClient(app)


def test_response_contains_generated_request_id() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_existing_request_id_is_preserved() -> None:
    request_id = "test-request-123"

    response = client.get(
        "/health",
        headers={"X-Request-ID": request_id},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id


def test_audit_log_contains_request_information(caplog) -> None:
    with caplog.at_level(
        logging.INFO,
        logger="customer360.audit",
    ):
        response = client.get(
            "/health",
            headers={"X-Request-ID": "audit-test-request"},
        )

    assert response.status_code == 200

    records = [
        record
        for record in caplog.records
        if record.name == "customer360.audit"
    ]

    assert records

    record = records[-1]

    assert record.event_type == "http_request"
    assert record.request_id == "audit-test-request"
    assert record.http_method == "GET"
    assert record.path == "/health"
    assert record.status_code == 200
    assert record.duration_ms >= 0
    assert record.client_ip


def test_json_formatter_includes_structured_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="customer360.audit",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP request completed",
        args=(),
        exc_info=None,
    )

    record.request_id = "formatter-test"
    record.status_code = 200

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "customer360.audit"
    assert payload["message"] == "HTTP request completed"
    assert payload["request_id"] == "formatter-test"
    assert payload["status_code"] == 200