import os
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text

from app.database import get_engine, init_database
from app.enrichment import DocumentEnrichmentRequest, DocumentEnrichmentResult, EnrichmentError, LlmDocumentEnricher
from app.models import AutomationRequest, AutomationRequestDetails, AutomationResult, MetricsSnapshot
from app.observability import CorrelationIdMiddleware, configure_logging, render_http_metrics
from app.security import ApiKeyMiddleware
from app.service import AutomationService

configure_logging(os.getenv("LOG_LEVEL", "INFO"))

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield

app = FastAPI(title="Enterprise Automation Orchestrator",version="1.3.0",description="API-first orchestration service for durable enterprise automation workloads across API and RPA execution channels.",lifespan=lifespan)
app.add_middleware(ApiKeyMiddleware)
app.add_middleware(CorrelationIdMiddleware)
service = AutomationService()

@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok"}

@app.get("/ready")
def readiness():
    dependencies: dict[str, str] = {}; ready = True
    try:
        with get_engine().connect() as connection: connection.execute(text("SELECT 1"))
        dependencies["database"] = "ok"
    except Exception: dependencies["database"] = "unavailable"; ready = False
    if os.getenv("DISPATCH_BACKEND", "database").strip().lower() == "redis":
        try:
            client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"),decode_responses=True,socket_connect_timeout=1,socket_timeout=1); client.ping(); dependencies["redis"] = "ok"
        except Exception: dependencies["redis"] = "unavailable"; ready = False
    payload = {"status": "ready" if ready else "not_ready", "dependencies": dependencies}
    return payload if ready else JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)

@app.post("/automation-requests", response_model=AutomationResult, status_code=status.HTTP_202_ACCEPTED)
def create_automation_request(request: AutomationRequest) -> AutomationResult: return service.submit(request)

@app.post("/enrichment/documents", response_model=DocumentEnrichmentResult)
def enrich_document(request: DocumentEnrichmentRequest) -> DocumentEnrichmentResult:
    try: return LlmDocumentEnricher().enrich(request)
    except EnrichmentError as exc: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

@app.get("/automation-requests/{request_id}", response_model=AutomationResult)
def get_automation_request(request_id: str) -> AutomationResult:
    result = service.get(request_id)
    if result is None: raise HTTPException(status_code=404, detail="Automation request not found")
    return result

@app.get("/automation-requests/{request_id}/audit", response_model=AutomationRequestDetails)
def get_automation_request_audit(request_id: str) -> AutomationRequestDetails:
    result = service.get_details(request_id)
    if result is None: raise HTTPException(status_code=404, detail="Automation request not found")
    return result

@app.post("/automation-requests/{request_id}/replay", response_model=AutomationResult)
def replay_dead_letter_request(request_id: str) -> AutomationResult:
    try: return service.replay_dead_letter(request_id)
    except KeyError as exc: raise HTTPException(status_code=404, detail="Automation request not found") from exc
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc

@app.get("/metrics", response_model=MetricsSnapshot)
def metrics() -> MetricsSnapshot: return service.metrics()

@app.get("/metrics/prometheus", response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    snapshot = service.metrics()
    lines = ["# HELP automation_requests_total Total automation requests accepted.","# TYPE automation_requests_total gauge",f"automation_requests_total {snapshot.total_requests}","# HELP automation_requests_by_status Automation requests by current lifecycle status.","# TYPE automation_requests_by_status gauge"]
    for request_status, count in sorted(snapshot.by_status.items()): lines.append(f'automation_requests_by_status{{status="{request_status}"}} {count}')
    lines.extend(["# HELP automation_queue_depth Requests waiting or scheduled for retry.","# TYPE automation_queue_depth gauge",f"automation_queue_depth {snapshot.queue_depth}","# HELP automation_retrying_count Requests currently waiting for retry.","# TYPE automation_retrying_count gauge",f"automation_retrying_count {snapshot.retrying_count}","# HELP automation_dead_letter_count Requests currently in dead letter.","# TYPE automation_dead_letter_count gauge",f"automation_dead_letter_count {snapshot.dead_letter_count}","# HELP automation_oldest_queued_age_seconds Age of oldest queued or retrying request.","# TYPE automation_oldest_queued_age_seconds gauge"])
    if snapshot.oldest_queued_age_seconds is not None: lines.append(f"automation_oldest_queued_age_seconds {snapshot.oldest_queued_age_seconds:.3f}")
    return "\n".join(lines) + "\n" + render_http_metrics()
