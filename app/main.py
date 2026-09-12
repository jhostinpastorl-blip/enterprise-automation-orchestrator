from fastapi import FastAPI, status

from app.models import AutomationRequest, AutomationResult
from app.service import AutomationService

app = FastAPI(
    title="Enterprise Automation Orchestrator",
    version="0.1.0",
    description="Routes enterprise automation requests through API or RPA execution channels.",
)
service = AutomationService()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/automation-requests",
    response_model=AutomationResult,
    status_code=status.HTTP_201_CREATED,
)
def create_automation_request(request: AutomationRequest) -> AutomationResult:
    return service.execute(request)
