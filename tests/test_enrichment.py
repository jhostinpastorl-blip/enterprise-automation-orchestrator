import json

import httpx
import pytest

from app.enrichment import (
    DocumentEnrichmentRequest,
    EnrichmentError,
    LlmDocumentEnricher,
)


def test_enrichment_validates_structured_output_and_skips_review_when_confident() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = {
            "document_type": "invoice",
            "extracted_fields": {"invoice_number": "INV-1001", "supplier": "ACME"},
            "confidence": 0.94,
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content)}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    enricher = LlmDocumentEnricher(
        base_url="https://llm.example.internal/v1",
        api_key="test-key",
        model="enterprise-model",
        client=client,
    )

    result = enricher.enrich(
        DocumentEnrichmentRequest(
            text="Invoice INV-1001 from ACME for customer C-42",
            review_threshold=0.80,
        )
    )

    assert result.document_type == "invoice"
    assert result.extracted_fields["invoice_number"] == "INV-1001"
    assert result.confidence == 0.94
    assert result.requires_human_review is False
    assert result.model == "enterprise-model"


def test_low_confidence_requires_human_review() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = {
            "document_type": "unknown",
            "extracted_fields": {},
            "confidence": 0.42,
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content)}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    enricher = LlmDocumentEnricher(
        base_url="https://llm.example.internal/v1",
        model="enterprise-model",
        client=client,
    )

    result = enricher.enrich(DocumentEnrichmentRequest(text="Ambiguous scanned content"))

    assert result.requires_human_review is True


def test_invalid_model_output_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    enricher = LlmDocumentEnricher(
        base_url="https://llm.example.internal/v1",
        model="enterprise-model",
        client=client,
    )

    with pytest.raises(EnrichmentError, match="Document enrichment failed"):
        enricher.enrich(DocumentEnrichmentRequest(text="invoice text"))


def test_missing_llm_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    with pytest.raises(EnrichmentError, match="LLM_BASE_URL and LLM_MODEL"):
        LlmDocumentEnricher().enrich(DocumentEnrichmentRequest(text="invoice text"))
