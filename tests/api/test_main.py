from fastapi.testclient import TestClient

from customer360.api.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")

    assert response.status_code == 200

    body = response.json()

    assert body["application"] == "Customer360 Platform"
    assert body["status"] == "running"


def test_get_customers():
    response = client.get("/customers")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_invalid_customer():
    response = client.get("/customers/does-not-exist")

    assert response.status_code == 404