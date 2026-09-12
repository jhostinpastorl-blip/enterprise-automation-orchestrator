from uuid import uuid4

from app.dispatch import DispatchQueue, get_dispatch_queue
from app.models import AutomationRequest, AutomationRequestDetails, AutomationResult, MetricsSnapshot
from app.repository import AutomationRepository


class AutomationService:
    def __init__(
        self,
        repository: AutomationRepository | None = None,
        dispatch: DispatchQueue | None = None,
    ) -> None:
        self.repository = repository or AutomationRepository()
        self.dispatch = dispatch

    def submit(self, request: AutomationRequest) -> AutomationResult:
        candidate_id = str(uuid4())
        request_id = self.repository.create(candidate_id, request)
        dispatcher = self.dispatch or get_dispatch_queue()
        if dispatcher.brokered:
            dispatcher.publish(request_id)
        result = self.repository.get(request_id)
        if result is None:
            raise RuntimeError(f"Request {request_id} was not persisted")
        return result

    def get(self, request_id: str) -> AutomationResult | None:
        return self.repository.get(request_id)

    def get_details(self, request_id: str) -> AutomationRequestDetails | None:
        return self.repository.get_details(request_id)

    def metrics(self) -> MetricsSnapshot:
        return self.repository.metrics()
