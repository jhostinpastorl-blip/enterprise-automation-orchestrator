import json
import logging
import threading
import time
import uuid
from collections import Counter
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")
_metrics_lock = threading.Lock()
_request_counts: Counter[tuple[str, str, int]] = Counter()
_request_duration_seconds: dict[tuple[str, str], list[float]] = {}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def observe_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    route = path if path in {"/health", "/ready", "/metrics", "/metrics/prometheus"} else "application"
    with _metrics_lock:
        _request_counts[(method, route, status_code)] += 1
        samples = _request_duration_seconds.setdefault((method, route), [])
        samples.append(duration_seconds)
        if len(samples) > 1000:
            del samples[:-1000]


def render_http_metrics() -> str:
    lines = [
        "# HELP http_requests_total HTTP requests handled by method, route group and status.",
        "# TYPE http_requests_total counter",
    ]
    with _metrics_lock:
        for (method, route, status_code), count in sorted(_request_counts.items()):
            lines.append(
                f'http_requests_total{{method="{method}",route="{route}",status="{status_code}"}} {count}'
            )
        lines.extend(
            [
                "# HELP http_request_duration_seconds Recent HTTP request latency samples.",
                "# TYPE http_request_duration_seconds summary",
            ]
        )
        for (method, route), samples in sorted(_request_duration_seconds.items()):
            if not samples:
                continue
            lines.append(
                f'http_request_duration_seconds_count{{method="{method}",route="{route}"}} {len(samples)}'
            )
            lines.append(
                f'http_request_duration_seconds_sum{{method="{method}",route="{route}"}} {sum(samples):.6f}'
            )
    return "\n".join(lines) + "\n"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        token = correlation_id_var.set(correlation_id)
        started = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_seconds = time.perf_counter() - started
            status_code = response.status_code if response is not None else 500
            observe_request(request.method, request.url.path, status_code, duration_seconds)
            logging.getLogger("http").info(
                "request_completed method=%s path=%s status=%s duration_ms=%s",
                request.method,
                request.url.path,
                status_code,
                round(duration_seconds * 1000, 2),
            )
            if response is not None:
                response.headers["X-Correlation-ID"] = correlation_id
            correlation_id_var.reset(token)
