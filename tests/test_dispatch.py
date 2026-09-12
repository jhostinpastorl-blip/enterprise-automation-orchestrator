from collections import deque

import pytest

from app.database import init_database
from app.dispatch import DatabaseDispatchQueue, RedisDispatchQueue
from app.models import AutomationRequest, ExecutionChannel
from app.repository import AutomationRepository
from app.service import AutomationService
from app.worker import ADAPTERS, AutomationWorker


class FakeRedis:
    def __init__(self) -> None:
        self.items: deque[str] = deque()

    def rpush(self, queue_name: str, request_id: str) -> None:
        self.items.append(request_id)

    def blpop(self, queue_name: str, timeout: int = 1):
        if not self.items:
            return None
        return queue_name, self.items.popleft()


class SuccessfulAdapter:
    def execute(self, request):
        return f"completed {request.target}"


@pytest.fixture
def repository(tmp_path, monkeypatch) -> AutomationRepository:
    monkeypatch.setenv("AUTOMATION_DB_PATH", str(tmp_path / "dispatch-test.db"))
    monkeypatch.delenv("AUTOMATION_DATABASE_URL", raising=False)
    init_database()
    return AutomationRepository()


def make_request() -> AutomationRequest:
    return AutomationRequest(
        process="customer_sync",
        target="crm",
        execution_channel=ExecutionChannel.API,
        payload={"customer_id": "C-1"},
        idempotency_key="customer-C-1-sync",
    )


def test_database_dispatch_is_not_brokered() -> None:
    dispatch = DatabaseDispatchQueue()
    assert dispatch.brokered is False
    dispatch.publish("request-1")
    assert dispatch.consume() is None


def test_redis_dispatch_round_trip() -> None:
    dispatch = RedisDispatchQueue(client=FakeRedis(), queue_name="test-queue")
    dispatch.publish("request-1")
    assert dispatch.consume() == "request-1"
    assert dispatch.consume() is None


def test_service_publishes_after_persistence(repository: AutomationRepository) -> None:
    dispatch = RedisDispatchQueue(client=FakeRedis(), queue_name="test-queue")
    service = AutomationService(repository=repository, dispatch=dispatch)

    result = service.submit(make_request())

    assert result.status.value == "queued"
    assert dispatch.consume() == result.request_id


def test_worker_consumes_broker_message_and_claims_specific_request(
    repository: AutomationRepository,
    monkeypatch,
) -> None:
    fake_redis = FakeRedis()
    dispatch = RedisDispatchQueue(client=fake_redis, queue_name="test-queue")
    service = AutomationService(repository=repository, dispatch=dispatch)
    result = service.submit(make_request())

    monkeypatch.setitem(ADAPTERS, ExecutionChannel.API, SuccessfulAdapter())
    worker = AutomationWorker(repository=repository, dispatch=dispatch, retry_delay_seconds=0)

    assert worker.run_once() is True
    persisted = repository.get(result.request_id)
    assert persisted is not None
    assert persisted.status.value == "completed"
    assert persisted.attempt_count == 1


def test_stale_broker_message_is_safely_ignored(repository: AutomationRepository) -> None:
    fake_redis = FakeRedis()
    dispatch = RedisDispatchQueue(client=fake_redis, queue_name="test-queue")
    dispatch.publish("missing-request")
    worker = AutomationWorker(repository=repository, dispatch=dispatch)

    assert worker.run_once() is True
