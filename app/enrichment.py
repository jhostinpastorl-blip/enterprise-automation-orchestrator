from __future__ import annotations

import json
import os
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError


class DocumentEnrichmentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    review_threshold: float = Field(default=0.80, ge=0.0, le=1.0)


class DocumentEnrichmentResult(BaseModel):
    document_type: str = Field(min_length=1, max_length=100)
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool
    provider: str
    model: str


class EnrichmentError(RuntimeError):
    pass


class LlmDocumentEnricher:
    """Validate an OpenAI-compatible chat-completions response into a typed result."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.client = client

    def enrich(self, request: DocumentEnrichmentRequest) -> DocumentEnrichmentResult:
        base_url = self.base_url or os.getenv("LLM_BASE_URL")
        api_key = self.api_key or os.getenv("LLM_API_KEY")
        model = self.model or os.getenv("LLM_MODEL")
        timeout = self.timeout_seconds or float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))

        if not base_url or not model:
            raise EnrichmentError("LLM_BASE_URL and LLM_MODEL are required")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        prompt = (
            "Classify the document and extract useful business fields. "
            "Return JSON only with keys document_type, extracted_fields and confidence. "
            "confidence must be between 0 and 1.\n\nDocument:\n" + request.text
        )
        payload = {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "You are a controlled document-enrichment component."},
                {"role": "user", "content": prompt},
            ],
        }

        try:
            response = self._post(f"{base_url.rstrip('/')}/chat/completions", payload, headers, timeout)
            response.raise_for_status()
            body = response.json()
            raw_content = body["choices"][0]["message"]["content"]
            parsed = json.loads(raw_content)
            confidence = float(parsed["confidence"])
            result = DocumentEnrichmentResult(
                document_type=parsed["document_type"],
                extracted_fields=parsed.get("extracted_fields", {}),
                confidence=confidence,
                requires_human_review=confidence < request.review_threshold,
                provider="openai-compatible",
                model=model,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            raise EnrichmentError(f"Document enrichment failed: {exc}") from exc

        return result

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
