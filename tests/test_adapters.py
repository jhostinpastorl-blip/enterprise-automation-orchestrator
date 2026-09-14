import json

import httpx
import pytest

from app.adapters import (
    AdapterConfigurationError,
    AdapterError,
    ApiAdapter,
    RetryableAdapterError,
    RpaAdapter,
    UiPathOrchestratorAdapter,
)
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


def test_api_adapter_preserves_retry_after_on_429() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "17"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ApiAdapter(base_url="https://example.internal", client=client)

    with pytest.raises(RetryableAdapterError) as exc_info:
        adapter.execute(make_request(ExecutionChannel.API))

    assert exc_info.value.retry_after_seconds == 17
    assert "rate limited" in str(exc_info.value)


def test_rpa_adapter_submits_vendor_neutral_job_contract(monkeypatch) -> None:
    monkeypatch.setenv("RPA_PROVIDER", "gateway")
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
    monkeypatch.setenv("RPA_PROVIDER", "gateway")
    monkeypatch.delenv("RPA_SUBMIT_URL", raising=False)
    with pytest.raises(AdapterConfigurationError):
        RpaAdapter().execute(make_request(ExecutionChannel.RPA))


def test_uipath_adapter_gets_token_and_starts_job(monkeypatch) -> None:
    monkeypatch.setenv("UIPATH_TOKEN_URL", "https://identity.example/connect/token")
    monkeypatch.setenv("UIPATH_ORCHESTRATOR_URL", "https://cloud.example/orchestrator_")
    monkeypatch.setenv("UIPATH_CLIENT_ID", "client-id")
    monkeypatch.setenv("UIPATH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("UIPATH_RELEASE_KEY", "release-key")
    monkeypatch.setenv("UIPATH_FOLDER_ID", "42")

    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            calls.append({"kind": "token", "body": request.content.decode()})
            return httpx.Response(200, json={"access_token": "access-token"})

        body = json.loads(request.content.decode())
        calls.append(
            {
                "kind": "job",
                "authorization": request.headers.get("authorization"),
                "folder": request.headers.get("x-uipath-organizationunitid"),
                "body": body,
                "url": str(request.url),
            }
        )
        return httpx.Response(201, json={"value": [{"Id": 123}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    detail = UiPathOrchestratorAdapter(client=client).execute(make_request(ExecutionChannel.RPA))

    assert detail == "UiPath Orchestrator job submitted"
    assert calls[0]["kind"] == "token"
    assert calls[1]["kind"] == "job"
    assert calls[1]["authorization"] == "Bearer access-token"
    assert calls[1]["folder"] == "42"
    assert str(calls[1]["url"]).endswith("/odata/Jobs/UiPath.Server.Configuration.OData.StartJobs")
    assert calls[1]["body"]["startInfo"]["ReleaseKey"] == "release-key"
    assert json.loads(calls[1]["body"]["startInfo"]["InputArguments"]) == {"status": "active"}


def test_rpa_adapter_delegates_to_uipath(monkeypatch) -> None:
    monkeypatch.setenv("RPA_PROVIDER", "uipath")
    monkeypatch.setenv("UIPATH_TOKEN_URL", "https://identity.example/connect/token")
    monkeypatch.setenv("UIPATH_ORCHESTRATOR_URL", "https://cloud.example/orchestrator_")
    monkeypatch.setenv("UIPATH_CLIENT_ID", "client-id")
    monkeypatch.setenv("UIPATH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("UIPATH_RELEASE_KEY", "release-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "access-token"})
        return httpx.Response(201, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    detail = RpaAdapter(client=client).execute(make_request(ExecutionChannel.RPA))
    assert detail == "UiPath Orchestrator job submitted"
