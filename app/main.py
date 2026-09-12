import os

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse

from app.database import init_database
from app.enrichment import (
    DocumentEnrichmentRequest,
    DocumentEnrichmentResult,
    EnrichmentError,
    LlmDocumentEnricher,
)
from app.models import AutomationRequest, AutomationRequestDetails, AutomationResult, MetricsSnapshot
from app.observability import CorrelationIdMiddleware, configure_logging
from app.security import ApiKeyMiddleware
from app.service import AutomationService

configure_logging(os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="Enterprise Automation Orchestrator",
    version="0.9.0",
    description=(
        "API-first orchestration service for durable enterprise automation workloads "
        "across API and RPA execution channels."
    ),
)
app.add_middleware(ApiKeyMiddleware)
app.add_middleware(CorrelationIdMiddleware)
service = AutomationService()


@app.on_event("startup")
def startup() -> None:
    init_database()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/automation-requests",
    response_model=AutomationResult,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_automation_request(request: AutomationRequest) -> AutomationResult:
    return service.submit(request)


@app.post("/enrichment/documents", response_model=DocumentEnrichmentResult)
def enrich_document(request: DocumentEnrichmentRequest) -> DocumentEnrichmentResult:
    try:
        return LlmDocumentEnricher().enrich(request)
    except EnrichmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@app.get("/automation-requests/{request_id}", response_model=AutomationResult)
def get_automation_request(request_id: str) -> AutomationResult:
    result = service.get(request_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation request not found")
    return result


@app.get("/automation-requests/{request_id}/audit", response_model=AutomationRequestDetails)
def get_automation_request_audit(request_id: str) -> AutomationRequestDetails:
    result = service.get_details(request_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation request not found")
    return result


@app.get("/metrics", response_model=MetricsSnapshot)
def metrics() -> MetricsSnapshot:
    return service.metrics()


@app.get("/metrics/prometheus", response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    snapshot = service.metrics()
    lines = [
        "# HELP automation_requests_total Total automation requests accepted.",
        "# TYPE automation_requests_total gauge",
        f"automation_requests_total {snapshot.total_requests}",
        "# HELP automation_requests_by_status Automation requests by current lifecycle status.",
        "# TYPE automation_requests_by_status gauge",
    ]
    for request_status, count in sorted(snapshot.by_status.items()):
        lines.append(f'automation_requests_by_status{{status="{request_status}"}} {count}')
    return "\n".join(lines) + "\n"
