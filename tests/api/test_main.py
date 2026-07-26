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