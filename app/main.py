import logging
import os

from fastapi import FastAPI, HTTPException, status

from app.database import init_database
from app.models import AutomationRequest, AutomationRequestDetails, AutomationResult, MetricsSnapshot
from app.service import AutomationService

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="Enterprise Automation Orchestrator",
    version="0.5.0",
    description=(
        "API-first orchestration service for durable enterprise automation workloads "
        "across API and RPA execution channels."
    ),
)
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
