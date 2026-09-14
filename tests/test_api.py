import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import ExecutionChannel
from app.worker import ADAPTERS, AutomationWorker


class SuccessfulAdapter:
    def execute(self, request):
        return f"simulated completion for {request.target}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "automation-test.db"
    monkeypatch.setenv("AUTOMATION_DB_PATH", str(db_path))
    monkeypatch.delenv("AUTOMATION_DATABASE_URL", raising=False)
    monkeypatch.setenv("DISPATCH_BACKEND", "database")
    monkeypatch.delenv("ORCHESTRATOR_API_KEY", raising=False)
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Correlation-ID"]


def test_preserves_client_correlation_id(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Correlation-ID": "trace-123"})
    assert response.headers["X-Correlation-ID"] == "trace-123"


def test_request_is_queued_then_completed_by_worker(client: TestClient, monkeypatch) -> None:
    monkeypatch.setitem(ADAPTERS, ExecutionChannel.API, SuccessfulAdapter())
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

    worker = AutomationWorker(retry_delay_seconds=0)
    assert worker.run_once() is True

    lookup = client.get(f"/automation-requests/{body['request_id']}")
    assert lookup.status_code == 200
    assert lookup.json()["status"] == "completed"


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
    assert first.json()["request_id"] == second.json()["request_id"]


def test_metrics_reports_queue_health(client: TestClient) -> None:
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
    body = response.json()
    assert response.status_code == 200
    assert body["total_requests"] == 1
    assert body["by_status"]["queued"] == 1
    assert body["queue_depth"] == 1
    assert body["retrying_count"] == 0
    assert body["dead_letter_count"] == 0
    assert body["oldest_queued_age_seconds"] is not None
    assert body["oldest_queued_age_seconds"] >= 0


def test_prometheus_metrics_endpoint(client: TestClient) -> None:
    client.post(
        "/automation-requests",
        json={
            "process": "sync",
            "target": "crm",
            "execution_channel": "api",
            "payload": {},
        },
    )
    text = client.get("/metrics/prometheus").text
    assert "automation_requests_total 1" in text
    assert "automation_queue_depth 1" in text
    assert "automation_retrying_count 0" in text
    assert "automation_dead_letter_count 0" in text
    assert "automation_oldest_queued_age_seconds" in text


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
