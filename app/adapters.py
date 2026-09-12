from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.models import AutomationRequest, ExecutionChannel


class AdapterError(RuntimeError):
    """Base exception raised by external execution adapters."""


class AdapterConfigurationError(AdapterError):
    """Raised when an adapter is missing required runtime configuration."""


class AutomationAdapter(ABC):
    @abstractmethod
    def execute(self, request: AutomationRequest) -> str:
        """Execute one automation request and return a short outcome."""


class ApiAdapter(AutomationAdapter):
    """Call a target system through a configurable HTTP API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.client = client

    def execute(self, request: AutomationRequest) -> str:
        base_url = self.base_url or os.getenv("TARGET_API_BASE_URL")
        if not base_url:
            raise AdapterConfigurationError(
                "TARGET_API_BASE_URL is required for API execution"
            )

        token = self.token or os.getenv("TARGET_API_TOKEN")
        timeout = self.timeout_seconds or float(os.getenv("TARGET_API_TIMEOUT_SECONDS", "10"))
        url = f"{base_url.rstrip('/')}/{request.target.lstrip('/')}"
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        try:
            response = self._post(url, request.payload, headers, timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AdapterError(f"API request failed for target '{request.target}': {exc}") from exc

        return self._response_detail(response, fallback=f"API request completed for '{request.target}'")

    def _post(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        if self.client is not None:
            return self.client.post(url, json=payload, headers=headers, timeout=timeout)
        with httpx.Client() as client:
            return client.post(url, json=payload, headers=headers, timeout=timeout)

    @staticmethod
    def _response_detail(response: httpx.Response, fallback: str) -> str:
        try:
            body = response.json()
        except ValueError:
            return fallback

        if isinstance(body, dict):
            for key in ("detail", "message", "status"):
                value = body.get(key)
                if value is not None:
                    return str(value)
        return fallback


class RpaAdapter(AutomationAdapter):
    """Submit work to an external RPA platform or gateway through HTTP."""

    def __init__(
        self,
        *,
        submit_url: str | None = None,
        token: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.submit_url = submit_url
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.client = client

    def execute(self, request: AutomationRequest) -> str:
        submit_url = self.submit_url or os.getenv("RPA_SUBMIT_URL")
        if not submit_url:
            raise AdapterConfigurationError("RPA_SUBMIT_URL is required for RPA execution")

        token = self.token or os.getenv("RPA_SUBMIT_TOKEN")
        timeout = self.timeout_seconds or float(os.getenv("RPA_SUBMIT_TIMEOUT_SECONDS", "10"))
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        body = {
            "process": request.process,
            "target": request.target,
            "payload": request.payload,
            "idempotency_key": request.idempotency_key,
        }

        try:
            response = self._post(submit_url, body, headers, timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AdapterError(f"RPA submission failed for process '{request.process}': {exc}") from exc

        return ApiAdapter._response_detail(
            response,
            fallback=f"RPA request submitted for process '{request.process}'",
        )

    def _post(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        if self.client is not None:
            return self.client.post(url, json=payload, headers=headers, timeout=timeout)
        with httpx.Client() as client:
            return client.post(url, json=payload, headers=headers, timeout=timeout)


ADAPTERS: dict[ExecutionChannel, AutomationAdapter] = {
    ExecutionChannel.API: ApiAdapter(),
    ExecutionChannel.RPA: RpaAdapter(),
}
