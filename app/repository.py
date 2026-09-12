import json
from datetime import UTC, datetime

from app.database import transaction
from app.models import AutomationRequest, AutomationResult, AutomationStatus, ExecutionChannel


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class AutomationRepository:
    def create(self, request_id: str, request: AutomationRequest) -> None:
        now = utc_now()
        with transaction() as connection:
            connection.execute(
                """
                INSERT INTO automation_requests (
                    request_id, process, target, execution_channel,
                    payload_json, status, detail, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    request.process,
                    request.target,
                    request.execution_channel.value,
                    json.dumps(request.payload),
                    AutomationStatus.ACCEPTED.value,
                    "Request accepted for processing",
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO automation_events (request_id, status, detail, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    request_id,
                    AutomationStatus.ACCEPTED.value,
                    "Request accepted for processing",
                    now,
                ),
            )

    def update_status(self, request_id: str, status: AutomationStatus, detail: str) -> None:
        now = utc_now()
        with transaction() as connection:
            connection.execute(
                """
                UPDATE automation_requests
                SET status = ?, detail = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (status.value, detail, now, request_id),
            )
            connection.execute(
                """
                INSERT INTO automation_events (request_id, status, detail, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (request_id, status.value, detail, now),
            )

    def get(self, request_id: str) -> AutomationResult | None:
        with transaction() as connection:
            row = connection.execute(
                """
                SELECT request_id, status, execution_channel, detail, created_at, updated_at
                FROM automation_requests
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()

        if row is None:
            return None

        return AutomationResult(
            request_id=row["request_id"],
            status=AutomationStatus(row["status"]),
            execution_channel=ExecutionChannel(row["execution_channel"]),
            detail=row["detail"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
