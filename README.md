# Enterprise Automation Orchestrator

A reference implementation for enterprise automation where one business process may require direct APIs, RPA and optional AI enrichment while still needing durable state, retries, auditability, security controls and observable execution.

The core design decision is simple: **RPA is an execution mechanism, not the system of record.** Business orchestration, lifecycle state and reliability controls stay outside the robot workflow.

## Live reference deployment

**API:** https://api-production-f93c7.up.railway.app

Railway runs separate **FastAPI API, worker, PostgreSQL and Redis services**. The API exposes liveness and dependency-aware readiness probes; `/ready` verifies database connectivity and Redis when broker-backed dispatch is enabled. Non-public API endpoints can be protected with `X-API-Key` through `ORCHESTRATOR_API_KEY`.

This is intentionally described as a **portfolio/reference cloud deployment**. It is not evidence of enterprise production scale, security certification, load-tested availability or live production UiPath credentials. The current Railway PostgreSQL container does not have a persistent Railway volume attached, so the cloud environment must not be represented as production-grade durable storage.

## What it demonstrates

- FastAPI + Pydantic API contracts
- direct HTTP integrations behind adapter boundaries
- vendor-neutral RPA gateway integration
- UiPath Orchestrator OAuth/OData job-submission boundary
- SQLAlchemy persistence with SQLite local mode and PostgreSQL distributed mode
- PostgreSQL worker claiming with `FOR UPDATE SKIP LOCKED`
- Redis-backed dispatch with PostgreSQL remaining authoritative
- asynchronous workers, idempotency, bounded retries and dead-letter state
- dead-letter replay with append-only lifecycle auditing
- downstream `429` / `Retry-After` handling
- exponential retry backoff with jitter and worker-local target cooldown
- Alembic schema migrations
- API-key protection, correlation IDs and structured JSON logging
- liveness and dependency-aware readiness probes
- queue depth, retry, dead-letter and oldest-work metrics
- Prometheus-style operational metrics
- OpenTelemetry FastAPI/HTTPX instrumentation and worker execution spans
- guarded LLM document enrichment with typed output and human-review controls
- repeatable synthetic evaluation harness
- Docker topologies, Ruff, unit tests and GitHub Actions CI
- distributed integration tests against real PostgreSQL and Redis service containers
- synthetic CI admission benchmark with percentile latency reporting
- container-build validation and Railway deployment
- ADRs documenting design decisions and trade-offs

## Architecture

```text
Client
  |
  v
FastAPI ---------------> PostgreSQL
  |                    state + audit
  | publish request ID       ^
  v                          |
Redis -----------------> Worker
                          |   |
                          |   +--> RPA / UiPath boundary
                          +------> Direct HTTP API
```

PostgreSQL is the authoritative state store. Redis carries request IDs for dispatch only. A worker must atomically claim persisted work before execution, so stale or duplicate broker messages do not by themselves create a second execution claim.

## Operating modes

### Local

```text
AUTOMATION_DB_PATH=automation.db
DISPATCH_BACKEND=database
```

### Distributed

```text
AUTOMATION_DATABASE_URL=postgresql+psycopg://...
DISPATCH_BACKEND=redis
REDIS_URL=redis://...
REDIS_QUEUE_NAME=automation:requests
```

Run the distributed reference topology locally:

```bash
docker compose -f compose.production.yaml up --build
```

## Reliability model

```text
queued -> running -> completed
queued -> running -> retrying -> running -> completed
queued -> running -> retrying -> ... -> dead_letter
                                  dead_letter -> queued -> running -> ...
```

Clients may provide an `idempotency_key`; repeated submissions return the existing persisted request. Transient failures use bounded exponential backoff with jitter. Downstream rate-limit hints are honored when available. Dead-letter work can be replayed explicitly through an audited operator action.

The current target cooldown is worker-local. It is not represented as distributed rate limiting across a worker fleet; Redis-backed shared throttling remains a future evolution.

## Integration strategy

The worker selects an adapter rather than embedding every integration inside orchestration logic.

- **Direct API:** preferred when the target exposes a stable supported interface.
- **RPA gateway:** used when UI automation is the appropriate execution mechanism.
- **UiPath Orchestrator:** client-credentials token + OData `StartJobs` boundary. The HTTP contract is tested with mocked responses; no live production tenant is claimed.

This keeps the API/RPA choice explicit and replaceable.

## Security and observability

When `ORCHESTRATOR_API_KEY` is configured, non-public endpoints require `X-API-Key`. Requests receive an `X-Correlation-ID`; application logs are structured; HTTP request count/latency observations are exposed alongside automation lifecycle metrics.

Operational endpoints:

```text
GET /health
GET /ready
GET /metrics
GET /metrics/prometheus
```

OpenTelemetry instruments FastAPI and outbound HTTPX traffic and creates worker execution spans. OTLP/HTTP export can be enabled with `OTEL_EXPORTER_OTLP_ENDPOINT`; local console inspection can be enabled with `OTEL_CONSOLE_EXPORTER=true`.

The current implementation does **not** propagate trace context through the Redis/PostgreSQL asynchronous boundary, so it must not be represented as complete end-to-end distributed tracing.

The current security model remains reference-level. A real enterprise deployment would normally add OAuth/OIDC, RBAC, stronger secret/network controls, dependency scanning and policy enforcement.

## Guarded LLM enrichment

`POST /enrichment/documents` calls a configurable OpenAI-compatible endpoint, validates structured output with Pydantic and flags low-confidence results for human review. Malformed output fails closed. Included evaluation cases are synthetic and demonstrate an evaluation workflow, not production model accuracy.

## Performance evidence

GitHub Actions includes a repeatable synthetic admission benchmark. One reference CI run with 500 requests and concurrency 25 accepted 500/500 requests with zero failures, measured 66.21 requests/second, p95 admission latency of 730.08 ms and p99 of 1619.25 ms.

These are **CI admission measurements**, not production or end-to-end automation throughput. See [`docs/performance-testing.md`](docs/performance-testing.md) for the environment, full percentile results, limitations and provisional engineering target.

## Schema migrations

Alembic is included for managed schema evolution. This replaces treating `metadata.create_all()` as the long-term production migration strategy and makes database changes reviewable and repeatable.

## CI validation

GitHub Actions validates four concerns independently:

1. Ruff quality checks plus unit tests.
2. Distributed integration against real PostgreSQL and Redis service containers.
3. Synthetic API-admission benchmark with percentile latency reporting.
4. Clean container image build.

The distributed test persists a request in PostgreSQL, publishes its ID to Redis, consumes it with the worker, atomically claims it and verifies lifecycle/audit state.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Worker:

```bash
python -m app.worker
```

## Engineering decisions

See [`docs/decisions/`](docs/decisions/) for ADRs covering persistence, asynchronous execution, AI boundaries, integration design, LLM guardrails, security/observability, distributed state/dispatch, dead-letter replay, throttling/backpressure and OpenTelemetry boundaries.

See [`docs/deployment-railway.md`](docs/deployment-railway.md) for the cloud reference topology and deployment configuration.

## Roadmap

- [x] API/RPA routing boundary
- [x] persistence and append-only audit trail
- [x] asynchronous worker execution
- [x] retries, idempotency and dead-letter handling
- [x] dead-letter replay with audit history
- [x] HTTP integration layer and UiPath boundary
- [x] downstream rate-limit handling
- [x] exponential backoff, jitter and target cooldown
- [x] guarded LLM enrichment and evaluation harness
- [x] PostgreSQL state + Redis dispatch
- [x] real PostgreSQL/Redis CI integration validation
- [x] readiness, linting and container-build gates
- [x] Railway reference deployment
- [x] Alembic schema migrations
- [x] operational queue and HTTP metrics
- [x] OpenTelemetry instrumentation with configurable OTLP export
- [x] reproducible CI admission benchmark with measured percentiles
- [ ] persistent managed cloud database/storage for the reference deployment
- [ ] enterprise identity with OAuth/OIDC and RBAC
- [ ] distributed trace-context propagation across async dispatch
- [ ] distributed PostgreSQL/Redis load characterization across repeated runs
- [ ] production-grade SLOs derived from a real service context

## Scope

This repository is evidence of **automation engineering and system-design capability**: selecting integration mechanisms, separating orchestration from execution, designing for recoverability and observability, testing distributed behavior, measuring a clearly scoped workload and deploying a reference topology.

It does **not** replace evidence from real professional production environments and should not be used to claim Architect/Lead seniority by itself.
