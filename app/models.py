from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionChannel(StrEnum):
    API = "api"
    RPA = "rpa"


class AutomationStatus(StrEnum):
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    FAILED = "failed"


class AutomationRequest(BaseModel):
    process: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)
    execution_channel: ExecutionChannel
    payload: dict[str, Any]


class AutomationResult(BaseModel):
    request_id: str
    status: AutomationStatus
    execution_channel: ExecutionChannel
    detail: str
    created_at: str
    updated_at: str
