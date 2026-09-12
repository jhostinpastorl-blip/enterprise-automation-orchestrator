from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionChannel(StrEnum):
    API = "api"
    RPA = "rpa"


class AutomationStatus(StrEnum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class AutomationRequest(BaseModel):
    process: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)
    execution_channel: ExecutionChannel
    payload: dict[str, Any]
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    max_attempts: int = Field(default=3, ge=1, le=10)


class AutomationResult(BaseModel):
    request_id: str
    status: AutomationStatus
    execution_channel: ExecutionChannel
    detail: str
    attempt_count: int = 0
    max_attempts: int = 3
    created_at: str
    updated_at: str


class AutomationEvent(BaseModel):
    status: AutomationStatus
    detail: str
    created_at: str


class AutomationRequestDetails(AutomationResult):
    events: list[AutomationEvent] = Field(default_factory=list)


class MetricsSnapshot(BaseModel):
    total_requests: int
    by_status: dict[str, int]
