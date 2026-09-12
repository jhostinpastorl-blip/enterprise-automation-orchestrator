import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.worker import AutomationWorker


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "automation-test.db"
    monkeypatch.setenv("AUTOMATION_DB_PATH", str(db_path))
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_is_queued_then_completed_by_worker(client: TestClient) -> None:
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
    assert response.status_code == 202
    assert body["status"] == "queued"

    worker = AutomationWorker(retry_delay_seconds=0)
    assert worker.run_once() is True

    lookup = client.get(f"/automation-requests/{body['request_id']}")
    assert lookup.status_code == 200
    assert lookup.json()["status"] == "completed"
    assert lookup.json()["attempt_count"] == 1

    audit = client.get(f"/automation-requests/{body['request_id']}/audit")
    statuses = [event["status"] for event in audit.json()["events"]]
    assert statuses == ["queued", "running", "completed"]


def test_idempotency_key_returns_same_request(client: TestClient) -> None:
    payload = {
        "process": "invoice_sync",
        "target": "erp",
        "execution_channel": "rpa",
        "payload": {"invoice_id": "INV-1001"},
        "idempotency_key": "invoice-1001-sync",
    }

    first = client.post("/automation-requests", json=payload)
    second = client.post("/automation-requests", json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["request_id"] == second.json()["request_id"]


def test_metrics_reports_status_counts(client: TestClient) -> None:
    client.post(
        "/automation-requests",
        json={
            "process": "sync",
            "target": "crm",
            "execution_channel": "api",
            "payload": {},
        },
    )

    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.json()["total_requests"] == 1
    assert response.json()["by_status"]["queued"] == 1


def test_returns_404_for_unknown_request(client: TestClient) -> None:
    response = client.get("/automation-requests/not-a-real-request")
    assert response.status_code == 404


def test_rejects_unknown_execution_channel(client: TestClient) -> None:
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
