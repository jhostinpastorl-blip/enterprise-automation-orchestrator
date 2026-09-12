from uuid import uuid4

from app.adapters import ADAPTERS
from app.models import AutomationRequest, AutomationResult, AutomationStatus


class AutomationService:
    def execute(self, request: AutomationRequest) -> AutomationResult:
        request_id = str(uuid4())
        adapter = ADAPTERS[request.execution_channel]

        try:
            detail = adapter.execute(request)
            status = AutomationStatus.COMPLETED
        except Exception as exc:
            # Later iterations will replace this boundary with structured logging and retry rules.
            detail = f"Execution failed: {exc}"
            status = AutomationStatus.FAILED

        return AutomationResult(
            request_id=request_id,
            status=status,
            execution_channel=request.execution_channel,
            detail=detail,
        )
