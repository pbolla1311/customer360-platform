import os

from fastapi.testclient import TestClient

os.environ["API_KEY"] = "test-api-key"

from customer360.api.main import app

client = TestClient(app)

AUTH_HEADERS = {"X-API-Key": "test-api-key"}


def test_root():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_get_customers():
    response = client.get(
        "/customers",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_invalid_customer():
    response = client.get(
        "/customers/does-not-exist",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404


def test_customers_requires_api_key():
    response = client.get("/customers")

    assert response.status_code == 401


def test_customers_rejects_invalid_api_key():
    response = client.get(
        "/customers",
        headers={"X-API-Key": "wrong-key"},
    )

    assert response.status_code == 401


def test_customer_id_rejects_empty_path_segment():
    response = client.get(
        "/customers/",
        headers=AUTH_HEADERS,
        follow_redirects=False,
    )

    assert response.status_code in {307, 404}


def test_customer_id_rejects_overly_long_value():
    response = client.get(
        f"/customers/{'a' * 129}",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422


def test_customer_id_rejects_invalid_characters():
    response = client.get(
        "/customers/customer%20id",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422


def test_security_headers_are_present():
    response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_cors_allows_configured_origin():
    response = client.options(
        "/customers",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == (
        "http://localhost:3000"
    )


def test_cors_rejects_unconfigured_origin():
    response = client.options(
        "/customers",
        headers={
            "Origin": "https://untrusted.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )

    assert "Access-Control-Allow-Origin" not in response.headers