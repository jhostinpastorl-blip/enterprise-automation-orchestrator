import os

import pytest
import redis

from app.database import init_database
from app.dispatch import RedisDispatchQueue
from app.models import AutomationRequest, ExecutionChannel
from app.repository import AutomationRepository
from app.service import AutomationService
from app.worker import ADAPTERS, AutomationWorker

pytestmark = pytest.mark.distributed


class SuccessfulAdapter:
    def execute(self, request):
        return f"distributed completion for {request.target}"


@pytest.mark.skipif(
    os.getenv("RUN_DISTRIBUTED_INTEGRATION") != "1",
    reason="requires PostgreSQL and Redis integration services",
)
def test_postgres_redis_request_lifecycle(monkeypatch) -> None:
    init_database()

    redis_url = os.environ["REDIS_URL"]
    redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    redis_client.flushdb()

    repository = AutomationRepository()
    dispatch = RedisDispatchQueue(
        redis_url=redis_url,
        queue_name="automation:integration-test",
        client=redis_client,
    )
    service = AutomationService(repository=repository, dispatch=dispatch)

    monkeypatch.setitem(ADAPTERS, ExecutionChannel.API, SuccessfulAdapter())

    submitted = service.submit(
        AutomationRequest(
            process="distributed_customer_sync",
            target="crm",
            execution_channel=ExecutionChannel.API,
            payload={"customer_id": "C-DISTRIBUTED-1"},
            idempotency_key="distributed-customer-1",
        )
    )

    assert submitted.status.value == "queued"
    assert redis_client.llen("automation:integration-test") == 1

    worker = AutomationWorker(
        repository=repository,
        dispatch=dispatch,
        retry_delay_seconds=0,
    )
    assert worker.run_once() is True

    completed = repository.get(submitted.request_id)
    assert completed is not None
    assert completed.status.value == "completed"
    assert completed.attempt_count == 1

    audit = repository.get_details(submitted.request_id)
    assert audit is not None
    assert [event.status.value for event in audit.events] == [
        "queued",
        "running",
        "completed",
    ]
