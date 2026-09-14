# ADR 011 - OpenTelemetry tracing boundary

## Status

Accepted.

## Context

Correlation IDs and structured logs help diagnose individual HTTP requests, but they do not provide timing relationships between API handling, outbound HTTP calls and worker execution. The reference implementation needs trace-level evidence without claiming a production observability platform that is not actually deployed.

## Decision

Use OpenTelemetry as the tracing API and SDK.

The FastAPI surface is automatically instrumented. Outbound HTTPX calls are automatically instrumented. The worker creates a manual `automation.execute` span with request, process, target and execution-channel attributes.

Trace export is configurable:

- `OTEL_EXPORTER_OTLP_ENDPOINT` enables OTLP/HTTP export to a compatible collector or backend.
- `OTEL_CONSOLE_EXPORTER=true` enables a console exporter for local inspection.
- With neither configured, instrumentation remains available without pretending that a production trace backend exists.

## Important limitation

The current reference implementation does **not** propagate OpenTelemetry trace context through Redis dispatch or persisted PostgreSQL state. API and worker spans can therefore be observed, but they should not be represented as one guaranteed end-to-end distributed trace across the asynchronous boundary.

A future distributed implementation should serialize a trace carrier with the dispatch message or persist trace context alongside the automation request, then extract it in the worker before starting execution spans.

## Consequences

Positive:

- standard tracing API instead of custom tracing semantics;
- HTTP server/client visibility;
- worker execution timing;
- optional vendor-neutral OTLP export;
- explicit observability boundary that can evolve later.

Trade-offs:

- extra dependencies and runtime overhead;
- trace export needs an external collector/backend to be operationally useful;
- asynchronous context propagation remains future work.

## Portfolio claim

This implementation demonstrates OpenTelemetry instrumentation and observability design choices. It does not by itself demonstrate operation of a production observability platform or complete cross-service trace propagation.
