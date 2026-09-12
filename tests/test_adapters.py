import httpx
import pytest

from app.adapters import AdapterConfigurationError, AdapterError, ApiAdapter, RpaAdapter
from app.models import AutomationRequest, ExecutionChannel


def make_request(channel: ExecutionChannel) -> AutomationRequest:
    return AutomationRequest(
        process="customer_update",
        target="crm/customers/C-10042",
        execution_channel=channel,
        payload={"status": "active"},
        idempotency_key="customer-C-10042-update",
    )


def test_api_adapter_posts_payload_and_uses_bearer_token() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"message": "customer updated"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ApiAdapter(
        base_url="https://example.internal/api",
        token="test-token",
        client=client,
    )

    detail = adapter.execute(make_request(ExecutionChannel.API))

    assert detail == "customer updated"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://example.internal/api/crm/customers/C-10042"
    assert captured["authorization"] == "Bearer test-token"
    assert '"status":"active"' in captured["body"]


def test_api_adapter_requires_base_url(monkeypatch) -> None:
    monkeypatch.delenv("TARGET_API_BASE_URL", raising=False)
    with pytest.raises(AdapterConfigurationError):
        ApiAdapter().execute(make_request(ExecutionChannel.API))


def test_api_adapter_wraps_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "temporarily unavailable"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ApiAdapter(base_url="https://example.internal", client=client)

    with pytest.raises(AdapterError, match="API request failed"):
        adapter.execute(make_request(ExecutionChannel.API))


def test_rpa_adapter_submits_vendor_neutral_job_contract() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = request.content.decode()
        return httpx.Response(202, json={"status": "accepted"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = RpaAdapter(
        submit_url="https://rpa-gateway.internal/jobs",
        token="rpa-token",
        client=client,
    )

    detail = adapter.execute(make_request(ExecutionChannel.RPA))

    assert detail == "accepted"
    assert captured["authorization"] == "Bearer rpa-token"
    assert '"process":"customer_update"' in captured["body"]
    assert '"idempotency_key":"customer-C-10042-update"' in captured["body"]


def test_rpa_adapter_requires_submission_url(monkeypatch) -> None:
    monkeypatch.delenv("RPA_SUBMIT_URL", raising=False)
    with pytest.raises(AdapterConfigurationError):
        RpaAdapter().execute(make_request(ExecutionChannel.RPA))
