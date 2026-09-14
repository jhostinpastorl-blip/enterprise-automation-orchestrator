import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.database import automation_events, automation_requests, transaction
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
        if request.idempotency_key:
            with transaction() as connection:
                existing = connection.execute(
                    select(automation_requests.c.request_id).where(
                        automation_requests.c.idempotency_key == request.idempotency_key
                    )
                ).scalar_one_or_none()
                if existing:
                    return str(existing)

        try:
            with transaction() as connection:
                connection.execute(
                    insert(automation_requests).values(
                        request_id=request_id,
                        idempotency_key=request.idempotency_key,
                        process=request.process,
                        target=request.target,
                        execution_channel=request.execution_channel.value,
                        payload_json=json.dumps(request.payload),
                        status=AutomationStatus.QUEUED.value,
                        detail="Request queued for processing",
                        attempt_count=0,
                        max_attempts=request.max_attempts,
                        next_attempt_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
                self._append_event(
                    connection,
                    request_id,
                    AutomationStatus.QUEUED,
                    "Request queued for processing",
                    now,
                )
            return request_id
        except IntegrityError:
            if not request.idempotency_key:
                raise
            with transaction() as connection:
                existing = connection.execute(
                    select(automation_requests.c.request_id).where(
                        automation_requests.c.idempotency_key == request.idempotency_key
                    )
                ).scalar_one_or_none()
            if existing is None:
                raise
            return str(existing)

    def claim_next(self) -> tuple[str, AutomationRequest] | None:
        now = utc_now()
        with transaction(immediate=True) as connection:
            statement = (
                select(automation_requests)
                .where(self._eligible_clause(now))
                .order_by(automation_requests.c.created_at)
                .limit(1)
            )
            if connection.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            row = connection.execute(statement).mappings().first()
            if row is None:
                return None
            return self._claim_row(connection, dict(row), now)

    def claim(self, request_id: str) -> tuple[str, AutomationRequest] | None:
        now = utc_now()
        with transaction(immediate=True) as connection:
            statement = select(automation_requests).where(
                and_(
                    automation_requests.c.request_id == request_id,
                    self._eligible_clause(now),
                )
            )
            if connection.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            row = connection.execute(statement).mappings().first()
            if row is None:
                return None
            return self._claim_row(connection, dict(row), now)

    def complete(self, request_id: str, detail: str) -> None:
        self.update_status(request_id, AutomationStatus.COMPLETED, detail)

    def fail_or_retry(self, request_id: str, detail: str, retry_delay_seconds: int) -> None:
        with transaction() as connection:
            row = connection.execute(
                select(
                    automation_requests.c.attempt_count,
                    automation_requests.c.max_attempts,
                ).where(automation_requests.c.request_id == request_id)
            ).mappings().first()
            if row is None:
                raise KeyError(request_id)

            now = datetime.now(UTC)
            exhausted = row["attempt_count"] >= row["max_attempts"]
            status = AutomationStatus.DEAD_LETTER if exhausted else AutomationStatus.RETRYING
            next_attempt_at = (
                None
                if exhausted
                else (now + timedelta(seconds=retry_delay_seconds)).isoformat()
            )
            message = (
                f"Moved to dead letter after {row['attempt_count']} attempts: {detail}"
                if exhausted
                else f"Retry scheduled after attempt {row['attempt_count']}: {detail}"
            )
            connection.execute(
                update(automation_requests)
                .where(automation_requests.c.request_id == request_id)
                .values(
                    status=status.value,
                    detail=message,
                    next_attempt_at=next_attempt_at,
                    updated_at=now.isoformat(),
                )
            )
            self._append_event(connection, request_id, status, message, now.isoformat())

    def replay_dead_letter(self, request_id: str) -> AutomationResult:
        now = utc_now()
        with transaction(immediate=True) as connection:
            statement = select(automation_requests).where(
                automation_requests.c.request_id == request_id
            )
            if connection.dialect.name == "postgresql":
                statement = statement.with_for_update()
            row = connection.execute(statement).mappings().first()
            if row is None:
                raise KeyError(request_id)
            if row["status"] != AutomationStatus.DEAD_LETTER.value:
                raise ValueError("Only dead-letter requests can be replayed")

            detail = (
                "Dead-letter replay requested by operator; "
                "attempt budget reset and request returned to queue"
            )
            connection.execute(
                update(automation_requests)
                .where(automation_requests.c.request_id == request_id)
                .values(
                    status=AutomationStatus.QUEUED.value,
                    detail=detail,
                    attempt_count=0,
                    next_attempt_at=now,
                    updated_at=now,
                )
            )
            self._append_event(
                connection,
                request_id,
                AutomationStatus.QUEUED,
                detail,
                now,
            )
            updated = connection.execute(
                select(
                    automation_requests.c.request_id,
                    automation_requests.c.status,
                    automation_requests.c.execution_channel,
                    automation_requests.c.detail,
                    automation_requests.c.attempt_count,
                    automation_requests.c.max_attempts,
                    automation_requests.c.created_at,
                    automation_requests.c.updated_at,
                ).where(automation_requests.c.request_id == request_id)
            ).mappings().one()
        return self._to_result(dict(updated))

    def update_status(self, request_id: str, status: AutomationStatus, detail: str) -> None:
        now = utc_now()
        with transaction() as connection:
            connection.execute(
                update(automation_requests)
                .where(automation_requests.c.request_id == request_id)
                .values(
                    status=status.value,
                    detail=detail,
                    next_attempt_at=None,
                    updated_at=now,
                )
            )
            self._append_event(connection, request_id, status, detail, now)

    def get(self, request_id: str) -> AutomationResult | None:
        with transaction() as connection:
            row = connection.execute(
                select(
                    automation_requests.c.request_id,
                    automation_requests.c.status,
                    automation_requests.c.execution_channel,
                    automation_requests.c.detail,
                    automation_requests.c.attempt_count,
                    automation_requests.c.max_attempts,
                    automation_requests.c.created_at,
                    automation_requests.c.updated_at,
                ).where(automation_requests.c.request_id == request_id)
            ).mappings().first()
        return self._to_result(dict(row)) if row else None

    def get_details(self, request_id: str) -> AutomationRequestDetails | None:
        result = self.get(request_id)
        if result is None:
            return None
        with transaction() as connection:
            rows = connection.execute(
                select(
                    automation_events.c.status,
                    automation_events.c.detail,
                    automation_events.c.created_at,
                )
                .where(automation_events.c.request_id == request_id)
                .order_by(automation_events.c.event_id)
            ).mappings().all()
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
        waiting_statuses = [
            AutomationStatus.QUEUED.value,
            AutomationStatus.RETRYING.value,
        ]
        with transaction() as connection:
            total = connection.execute(
                select(func.count()).select_from(automation_requests)
            ).scalar_one()
            rows = connection.execute(
                select(
                    automation_requests.c.status,
                    func.count().label("count"),
                ).group_by(automation_requests.c.status)
            ).mappings().all()
            oldest = connection.execute(
                select(func.min(automation_requests.c.created_at)).where(
                    automation_requests.c.status.in_(waiting_statuses)
                )
            ).scalar_one_or_none()

        by_status = {str(row["status"]): int(row["count"]) for row in rows}
        queue_depth = (
            by_status.get(AutomationStatus.QUEUED.value, 0)
            + by_status.get(AutomationStatus.RETRYING.value, 0)
        )
        oldest_age = None
        if oldest:
            oldest_dt = datetime.fromisoformat(str(oldest))
            if oldest_dt.tzinfo is None:
                oldest_dt = oldest_dt.replace(tzinfo=UTC)
            oldest_age = max(0.0, (datetime.now(UTC) - oldest_dt).total_seconds())

        return MetricsSnapshot(
            total_requests=int(total),
            by_status=by_status,
            queue_depth=queue_depth,
            retrying_count=by_status.get(AutomationStatus.RETRYING.value, 0),
            dead_letter_count=by_status.get(AutomationStatus.DEAD_LETTER.value, 0),
            oldest_queued_age_seconds=oldest_age,
        )

    @staticmethod
    def _eligible_clause(now: str):
        return and_(
            automation_requests.c.status.in_(
                [AutomationStatus.QUEUED.value, AutomationStatus.RETRYING.value]
            ),
            or_(
                automation_requests.c.next_attempt_at.is_(None),
                automation_requests.c.next_attempt_at <= now,
            ),
        )

    def _claim_row(self, connection, row: dict, now: str) -> tuple[str, AutomationRequest]:
        attempt_count = int(row["attempt_count"]) + 1
        detail = f"Execution attempt {attempt_count} started"
        connection.execute(
            update(automation_requests)
            .where(automation_requests.c.request_id == row["request_id"])
            .values(
                status=AutomationStatus.RUNNING.value,
                detail=detail,
                attempt_count=attempt_count,
                updated_at=now,
            )
        )
        self._append_event(
            connection,
            row["request_id"],
            AutomationStatus.RUNNING,
            detail,
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
        return str(row["request_id"]), request

    @staticmethod
    def _append_event(
        connection,
        request_id: str,
        status: AutomationStatus,
        detail: str,
        created_at: str,
    ) -> None:
        connection.execute(
            insert(automation_events).values(
                request_id=request_id,
                status=status.value,
                detail=detail,
                created_at=created_at,
            )
        )

    @staticmethod
    def _to_result(row: dict) -> AutomationResult:
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
