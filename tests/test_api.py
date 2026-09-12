from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_routes_request_to_api_adapter() -> None:
    response = client.post(
        "/automation-requests",
        json={
            "process": "customer_update",
            "target": "crm",
            "execution_channel": "api",
            "payload": {"customer_id": "C-10042"},
        },
    )

    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "completed"
    assert body["execution_channel"] == "api"
    assert "crm" in body["detail"]


def test_rejects_unknown_execution_channel() -> None:
    response = client.post(
        "/automation-requests",
        json={
            "process": "customer_update",
            "target": "legacy_crm",
            "execution_channel": "desktop",
            "payload": {},
        },
    )

    assert response.status_code == 422
