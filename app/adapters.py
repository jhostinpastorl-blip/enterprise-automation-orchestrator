from abc import ABC, abstractmethod

from app.models import AutomationRequest, ExecutionChannel


class AutomationAdapter(ABC):
    @abstractmethod
    def execute(self, request: AutomationRequest) -> str:
        """Execute one automation request and return a short outcome."""


class ApiAdapter(AutomationAdapter):
    def execute(self, request: AutomationRequest) -> str:
        # A real implementation will call the target system through an HTTP client.
        return f"API execution prepared for target '{request.target}'"


class RpaAdapter(AutomationAdapter):
    def execute(self, request: AutomationRequest) -> str:
        # The orchestrator should submit work to an RPA platform, not automate the UI itself.
        return f"RPA execution prepared for target '{request.target}'"


ADAPTERS: dict[ExecutionChannel, AutomationAdapter] = {
    ExecutionChannel.API: ApiAdapter(),
    ExecutionChannel.RPA: RpaAdapter(),
}
