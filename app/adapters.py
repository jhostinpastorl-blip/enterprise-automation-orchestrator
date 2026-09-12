from __future__ import annotations

import json
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
            raise AdapterConfigurationError("TARGET_API_BASE_URL is required for API execution")

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


class UiPathOrchestratorAdapter(AutomationAdapter):
    """Start a UiPath Orchestrator job through the official HTTP/OData surface."""

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self.client = client

    def execute(self, request: AutomationRequest) -> str:
        token_url = os.getenv("UIPATH_TOKEN_URL")
        orchestrator_url = os.getenv("UIPATH_ORCHESTRATOR_URL")
        client_id = os.getenv("UIPATH_CLIENT_ID")
        client_secret = os.getenv("UIPATH_CLIENT_SECRET")
        release_key = os.getenv("UIPATH_RELEASE_KEY")
        folder_id = os.getenv("UIPATH_FOLDER_ID")
        timeout = float(os.getenv("UIPATH_TIMEOUT_SECONDS", "15"))

        missing = [
            name
            for name, value in {
                "UIPATH_TOKEN_URL": token_url,
                "UIPATH_ORCHESTRATOR_URL": orchestrator_url,
                "UIPATH_CLIENT_ID": client_id,
                "UIPATH_CLIENT_SECRET": client_secret,
                "UIPATH_RELEASE_KEY": release_key,
            }.items()
            if not value
        ]
        if missing:
            raise AdapterConfigurationError(f"Missing UiPath configuration: {', '.join(missing)}")

        try:
            token_response = self._request_token(
                token_url=token_url,
                client_id=client_id,
                client_secret=client_secret,
                timeout=timeout,
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]

            headers = {"Authorization": f"Bearer {access_token}"}
            if folder_id:
                headers["X-UIPATH-OrganizationUnitId"] = folder_id

            start_url = (
                f"{orchestrator_url.rstrip('/')}/odata/Jobs/"
                "UiPath.Server.Configuration.OData.StartJobs"
            )
            body = {
                "startInfo": {
                    "ReleaseKey": release_key,
                    "Strategy": "Specific",
                    "RobotIds": [],
                    "JobsCount": 0,
                    "Source": "Manual",
                    "InputArguments": json.dumps(request.payload),
                }
            }
            response = self._post(start_url, body, headers, timeout)
            response.raise_for_status()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise AdapterError(f"UiPath Orchestrator submission failed: {exc}") from exc

        return "UiPath Orchestrator job submitted"

    def _request_token(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        timeout: float,
    ) -> httpx.Response:
        data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if self.client is not None:
            return self.client.post(token_url, data=data, timeout=timeout)
        with httpx.Client() as client:
            return client.post(token_url, data=data, timeout=timeout)

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


class RpaAdapter(AutomationAdapter):
    """Submit work to UiPath or a vendor-neutral external RPA gateway."""

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
        if os.getenv("RPA_PROVIDER", "gateway").lower() == "uipath":
            return UiPathOrchestratorAdapter(client=self.client).execute(request)

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
