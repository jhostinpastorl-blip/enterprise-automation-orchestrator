import logging
import os
import time

from app.adapters import ADAPTERS
from app.repository import AutomationRepository

logger = logging.getLogger(__name__)


class AutomationWorker:
    def __init__(
        self,
        repository: AutomationRepository | None = None,
        retry_delay_seconds: int | None = None,
    ) -> None:
        self.repository = repository or AutomationRepository()
        self.retry_delay_seconds = retry_delay_seconds or int(os.getenv("RETRY_DELAY_SECONDS", "5"))

    def run_once(self) -> bool:
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
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    AutomationWorker().run_forever(
        poll_interval_seconds=float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "1"))
    )


if __name__ == "__main__":
    main()
