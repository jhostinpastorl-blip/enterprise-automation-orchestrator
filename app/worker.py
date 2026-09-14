import logging
import os
import random
import time

from app.adapters import ADAPTERS, RetryableAdapterError
from app.dispatch import DispatchQueue, get_dispatch_queue
from app.observability import configure_logging
from app.repository import AutomationRepository
from app.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class AutomationWorker:
    def __init__(
        self,
        repository: AutomationRepository | None = None,
        retry_delay_seconds: int | None = None,
        dispatch: DispatchQueue | None = None,
    ) -> None:
        self.repository = repository or AutomationRepository()
        self.retry_delay_seconds = (
            int(os.getenv("RETRY_DELAY_SECONDS", "5"))
            if retry_delay_seconds is None
            else retry_delay_seconds
        )
        self.max_retry_delay_seconds = int(os.getenv("MAX_RETRY_DELAY_SECONDS", "300"))
        self.jitter_ratio = float(os.getenv("RETRY_JITTER_RATIO", "0.20"))
        self.dispatch = dispatch
        self._target_cooldowns: dict[str, float] = {}

    def _backoff(self, attempt: int) -> int:
        base = min(
            self.max_retry_delay_seconds,
            self.retry_delay_seconds * (2 ** max(0, attempt - 1)),
        )
        jitter = base * self.jitter_ratio * random.random()
        return max(0, int(base + jitter))

    def run_once(self) -> bool:
        dispatcher = self.dispatch or get_dispatch_queue()
        claimed = None
        if dispatcher.brokered:
            request_id = dispatcher.consume(timeout_seconds=1)
            if request_id is not None:
                claimed = self.repository.claim(request_id)
                if claimed is None:
                    logger.info("stale_dispatch_message request_id=%s", request_id)
            if claimed is None:
                claimed = self.repository.claim_next()
        else:
            claimed = self.repository.claim_next()

        if claimed is None:
            return False

        request_id, request = claimed
        cooldown_until = self._target_cooldowns.get(request.target, 0.0)
        if cooldown_until > time.monotonic():
            delay = max(1, int(cooldown_until - time.monotonic()))
            logger.warning(
                "target_backpressure request_id=%s target=%s retry_after_seconds=%s",
                request_id,
                request.target,
                delay,
            )
            self.repository.fail_or_retry(
                request_id,
                f"Target '{request.target}' is cooling down",
                delay,
            )
            return True

        adapter = ADAPTERS[request.execution_channel]
        logger.info(
            "automation_execution_started request_id=%s process=%s target=%s channel=%s",
            request_id,
            request.process,
            request.target,
            request.execution_channel.value,
        )

        with tracer.start_as_current_span(
            "automation.execute",
            attributes={
                "automation.request_id": request_id,
                "automation.process": request.process,
                "automation.target": request.target,
                "automation.channel": request.execution_channel.value,
            },
        ):
            try:
                detail = adapter.execute(request)
            except RetryableAdapterError as exc:
                result = self.repository.get(request_id)
                attempt = result.attempt_count if result is not None else 1
                retry_delay = (
                    exc.retry_after_seconds
                    if exc.retry_after_seconds is not None
                    else self._backoff(attempt)
                )
                if exc.retry_after_seconds is not None:
                    self._target_cooldowns[request.target] = time.monotonic() + retry_delay
                logger.warning(
                    "automation_execution_rate_limited request_id=%s target=%s retry_after_seconds=%s",
                    request_id,
                    request.target,
                    retry_delay,
                )
                self.repository.fail_or_retry(
                    request_id,
                    detail=str(exc),
                    retry_delay_seconds=retry_delay,
                )
            except Exception as exc:
                result = self.repository.get(request_id)
                attempt = result.attempt_count if result is not None else 1
                retry_delay = self._backoff(attempt)
                logger.exception(
                    "automation_execution_failed request_id=%s retry_after_seconds=%s",
                    request_id,
                    retry_delay,
                )
                self.repository.fail_or_retry(
                    request_id,
                    detail=str(exc),
                    retry_delay_seconds=retry_delay,
                )
            else:
                self._target_cooldowns.pop(request.target, None)
                self.repository.complete(request_id, detail)
                logger.info("automation_execution_completed request_id=%s", request_id)
        return True

    def run_forever(self, poll_interval_seconds: float = 1.0) -> None:
        logger.info("automation_worker_started poll_interval_seconds=%s", poll_interval_seconds)
        while True:
            worked = self.run_once()
            if not worked:
                time.sleep(poll_interval_seconds)


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    AutomationWorker().run_forever(
        poll_interval_seconds=float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "1"))
    )


if __name__ == "__main__":
    main()
