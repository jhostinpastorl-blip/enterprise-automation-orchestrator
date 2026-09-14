from __future__ import annotations

import os
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor

_configured = False
_httpx_instrumented = False


def configure_telemetry(service_name: str = "enterprise-automation-orchestrator") -> None:
    global _configured, _httpx_instrumented
    if _configured:
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    elif os.getenv("OTEL_CONSOLE_EXPORTER", "false").lower() == "true":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    if not _httpx_instrumented:
        HTTPXClientInstrumentor().instrument()
        _httpx_instrumented = True
    _configured = True


def instrument_fastapi(app: Any) -> None:
    configure_telemetry()
    FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str = __name__):
    configure_telemetry()
    return trace.get_tracer(name)
