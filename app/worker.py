import logging
import os
import time

from app.adapters import ADAPTERS, RetryableAdapterError
from app.dispatch import DispatchQueue, get_dispatch_queue
from app.observability import configure_logging
from app.repository import AutomationRepository

logger = logging.getLogger(__name__)


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
        self.dispatch = dispatch

    def run_once(self) -> bool:
        dispatcher = self.dispatch or get_dispatch_queue()
        claimed = None

        if dispatcher.brokered:
            request_id = dispatcher.consume(timeout_seconds=1)
            if request_id is not None:
                claimed = self.repository.claim(request_id)
                if claimed is None:
                    logger.info("stale_dispatch_message request_id=%s", request_id)

            # Durable state remains authoritative. This fallback recovers work if a
            # broker message is lost and also picks up retrying rows after their delay.
            if claimed is None:
                claimed = self.repository.claim_next()
        else:
            claimed = self.repository.claim_next()

        if claimed is None:
            return False

        request_id, request = claimed
        adapter = ADAPTERS[request.execution_channel]
        logger.info(
            "automation_execution_started request_id=%s process=%s target=%s channel=%s",
            request_id,
            request.process,
            request.target,
            request.execution_channel.value,
        )

        try:
            detail = adapter.execute(request)
        except RetryableAdapterError as exc:
            retry_delay = (
                exc.retry_after_seconds
                if exc.retry_after_seconds is not None
                else self.retry_delay_seconds
            )
            logger.warning(
                "automation_execution_rate_limited request_id=%s retry_after_seconds=%s",
                request_id,
                retry_delay,
            )
            self.repository.fail_or_retry(
                request_id,
                detail=str(exc),
                retry_delay_seconds=retry_delay,
            )
        except Exception as exc:
            logger.exception("automation_execution_failed request_id=%s", request_id)
            self.repository.fail_or_retry(
                request_id,
                detail=str(exc),
                retry_delay_seconds=self.retry_delay_seconds,
            )
        else:
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
