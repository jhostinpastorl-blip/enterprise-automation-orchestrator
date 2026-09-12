from fastapi import FastAPI, HTTPException, status

from app.database import init_database
from app.models import AutomationRequest, AutomationResult
from app.service import AutomationService

app = FastAPI(
    title="Enterprise Automation Orchestrator",
    version="0.2.0",
    description="Routes enterprise automation requests through API or RPA execution channels with persistent lifecycle tracking.",
)


@app.on_event("startup")
def startup() -> None:
    init_database()


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


@app.get("/automation-requests/{request_id}", response_model=AutomationResult)
def get_automation_request(request_id: str) -> AutomationResult:
    result = service.get(request_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation request not found")
    return result
