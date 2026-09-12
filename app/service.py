from uuid import uuid4

from app.adapters import ADAPTERS
from app.models import AutomationRequest, AutomationResult, AutomationStatus
from app.repository import AutomationRepository


class AutomationService:
    def __init__(self, repository: AutomationRepository | None = None) -> None:
        self.repository = repository or AutomationRepository()

    def execute(self, request: AutomationRequest) -> AutomationResult:
        request_id = str(uuid4())
        self.repository.create(request_id, request)
        adapter = ADAPTERS[request.execution_channel]

        try:
            detail = adapter.execute(request)
            status = AutomationStatus.COMPLETED
        except Exception as exc:
            detail = f"Execution failed: {exc}"
            status = AutomationStatus.FAILED

        self.repository.update_status(request_id, status, detail)
        result = self.repository.get(request_id)
        if result is None:
            raise RuntimeError(f"Request {request_id} was not persisted")

        return result

    def get(self, request_id: str) -> AutomationResult | None:
        return self.repository.get(request_id)
