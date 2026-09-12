import json
from datetime import UTC, datetime, timedelta

from app.database import transaction
from app.models import (
    AutomationEvent,
    AutomationRequest,
    AutomationRequestDetails,
    AutomationResult,
    AutomationStatus,
    ExecutionChannel,
    MetricsSnapshot,
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class AutomationRepository:
    def create(self, request_id: str, request: AutomationRequest) -> str:
        now = utc_now()
        with transaction() as connection:
            if request.idempotency_key:
                existing = connection.execute(
                    "SELECT request_id FROM automation_requests WHERE idempotency_key = ?",
                    (request.idempotency_key,),
                ).fetchone()
                if existing:
                    return existing["request_id"]

            connection.execute(
                """
                INSERT INTO automation_requests (
                    request_id, idempotency_key, process, target, execution_channel,
                    payload_json, status, detail, attempt_count, max_attempts,
                    next_attempt_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    request.idempotency_key,
                    request.process,
                    request.target,
                    request.execution_channel.value,
                    json.dumps(request.payload),
                    AutomationStatus.QUEUED.value,
                    "Request queued for processing",
                    request.max_attempts,
                    now,
                    now,
                    now,
                ),
            )
            self._append_event(
                connection,
                request_id,
                AutomationStatus.QUEUED,
                "Request queued for processing",
                now,
            )
        return request_id

    def claim_next(self) -> tuple[str, AutomationRequest] | None:
        now = utc_now()
        with transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT * FROM automation_requests
                WHERE status IN (?, ?) AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY created_at
                LIMIT 1
                """,
                (AutomationStatus.QUEUED.value, AutomationStatus.RETRYING.value, now),
            ).fetchone()
            if row is None:
                return None

            attempt_count = row["attempt_count"] + 1
            connection.execute(
                """
                UPDATE automation_requests
                SET status = ?, detail = ?, attempt_count = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (
                    AutomationStatus.RUNNING.value,
                    f"Execution attempt {attempt_count} started",
                    attempt_count,
                    now,
                    row["request_id"],
                ),
            )
            self._append_event(
                connection,
                row["request_id"],
                AutomationStatus.RUNNING,
                f"Execution attempt {attempt_count} started",
                now,
            )

        request = AutomationRequest(
            process=row["process"],
            target=row["target"],
            execution_channel=ExecutionChannel(row["execution_channel"]),
            payload=json.loads(row["payload_json"]),
            idempotency_key=row["idempotency_key"],
            max_attempts=row["max_attempts"],
        )
        return row["request_id"], request

    def complete(self, request_id: str, detail: str) -> None:
        self.update_status(request_id, AutomationStatus.COMPLETED, detail)

    def fail_or_retry(self, request_id: str, detail: str, retry_delay_seconds: int) -> None:
        with transaction() as connection:
            row = connection.execute(
                "SELECT attempt_count, max_attempts FROM automation_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise KeyError(request_id)

            now = datetime.now(UTC)
            exhausted = row["attempt_count"] >= row["max_attempts"]
            status = AutomationStatus.DEAD_LETTER if exhausted else AutomationStatus.RETRYING
            next_attempt_at = None if exhausted else (now + timedelta(seconds=retry_delay_seconds)).isoformat()
            message = (
                f"Moved to dead letter after {row['attempt_count']} attempts: {detail}"
                if exhausted
                else f"Retry scheduled after attempt {row['attempt_count']}: {detail}"
            )
            connection.execute(
                """
                UPDATE automation_requests
                SET status = ?, detail = ?, next_attempt_at = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (status.value, message, next_attempt_at, now.isoformat(), request_id),
            )
            self._append_event(connection, request_id, status, message, now.isoformat())

    def update_status(self, request_id: str, status: AutomationStatus, detail: str) -> None:
        now = utc_now()
        with transaction() as connection:
            connection.execute(
                """
                UPDATE automation_requests
                SET status = ?, detail = ?, next_attempt_at = NULL, updated_at = ?
                WHERE request_id = ?
                """,
                (status.value, detail, now, request_id),
            )
            self._append_event(connection, request_id, status, detail, now)

    def get(self, request_id: str) -> AutomationResult | None:
        with transaction() as connection:
            row = connection.execute(
                """
                SELECT request_id, status, execution_channel, detail,
                       attempt_count, max_attempts, created_at, updated_at
                FROM automation_requests WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
        return self._to_result(row) if row else None

    def get_details(self, request_id: str) -> AutomationRequestDetails | None:
        result = self.get(request_id)
        if result is None:
            return None
        with transaction() as connection:
            rows = connection.execute(
                """
                SELECT status, detail, created_at
                FROM automation_events WHERE request_id = ? ORDER BY event_id
                """,
                (request_id,),
            ).fetchall()
        return AutomationRequestDetails(
            **result.model_dump(),
            events=[
                AutomationEvent(
                    status=AutomationStatus(row["status"]),
                    detail=row["detail"],
                    created_at=row["created_at"],
                )
                for row in rows
            ],
        )

    def metrics(self) -> MetricsSnapshot:
        with transaction() as connection:
            total = connection.execute("SELECT COUNT(*) AS count FROM automation_requests").fetchone()["count"]
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM automation_requests GROUP BY status"
            ).fetchall()
        return MetricsSnapshot(
            total_requests=total,
            by_status={row["status"]: row["count"] for row in rows},
        )

    @staticmethod
    def _append_event(connection, request_id: str, status: AutomationStatus, detail: str, created_at: str) -> None:
        connection.execute(
            "INSERT INTO automation_events (request_id, status, detail, created_at) VALUES (?, ?, ?, ?)",
            (request_id, status.value, detail, created_at),
        )

    @staticmethod
    def _to_result(row) -> AutomationResult:
        return AutomationResult(
            request_id=row["request_id"],
            status=AutomationStatus(row["status"]),
            execution_channel=ExecutionChannel(row["execution_channel"]),
            detail=row["detail"],
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
