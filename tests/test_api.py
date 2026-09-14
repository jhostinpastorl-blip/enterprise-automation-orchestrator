import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import ExecutionChannel
from app.worker import ADAPTERS, AutomationWorker


class SuccessfulAdapter:
    def execute(self, request):
        return f"simulated completion for {request.target}"


class FailingAdapter:
    def execute(self, request):
        raise RuntimeError(f"simulated failure for {request.target}")


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


def test_api_key_protects_non_public_endpoints(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_API_KEY", "secret-key")

    unauthorized = client.get("/metrics")
    authorized = client.get("/metrics", headers={"X-API-Key": "secret-key"})
    health = client.get("/health")

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert health.status_code == 200


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


def test_dead_letter_can_be_replayed_and_completed(client: TestClient, monkeypatch) -> None:
    monkeypatch.setitem(ADAPTERS, ExecutionChannel.API, FailingAdapter())

    response = client.post(
        "/automation-requests",
        json={
            "process": "invoice_posting",
            "target": "erp",
            "execution_channel": "api",
            "payload": {"invoice_id": "INV-9001"},
            "max_attempts": 1,
        },
    )
    request_id = response.json()["request_id"]

    worker = AutomationWorker(retry_delay_seconds=0)
    assert worker.run_once() is True
    dead_letter = client.get(f"/automation-requests/{request_id}")
    assert dead_letter.json()["status"] == "dead_letter"
    assert dead_letter.json()["attempt_count"] == 1

    replay = client.post(f"/automation-requests/{request_id}/replay")
    assert replay.status_code == 200
    assert replay.json()["status"] == "queued"
    assert replay.json()["attempt_count"] == 0

    monkeypatch.setitem(ADAPTERS, ExecutionChannel.API, SuccessfulAdapter())
    assert worker.run_once() is True
    completed = client.get(f"/automation-requests/{request_id}")
    assert completed.json()["status"] == "completed"

    audit = client.get(f"/automation-requests/{request_id}/audit")
    statuses = [event["status"] for event in audit.json()["events"]]
    assert statuses == ["queued", "running", "dead_letter", "queued", "running", "completed"]


def test_replay_rejects_request_that_is_not_dead_letter(client: TestClient) -> None:
    response = client.post(
        "/automation-requests",
        json={
            "process": "sync",
            "target": "crm",
            "execution_channel": "api",
            "payload": {},
        },
    )
    request_id = response.json()["request_id"]

    replay = client.post(f"/automation-requests/{request_id}/replay")
    assert replay.status_code == 409
    assert replay.json()["detail"] == "Only dead-letter requests can be replayed"


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
    response = client.get("/metrics/prometheus")
    assert response.status_code == 200
    assert "automation_requests_total 1" in response.text
    assert 'automation_requests_by_status{status="queued"} 1' in response.text


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
