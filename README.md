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
- append-only lifecycle audit events
- Alembic schema migrations
- API-key protection, correlation IDs and structured JSON logging
- liveness and dependency-aware readiness probes
- operational HTTP latency/request metrics plus Prometheus-style automation metrics
- guarded LLM document enrichment with typed output and human-review controls
- repeatable synthetic evaluation harness
- Docker topologies, Ruff, unit tests and GitHub Actions CI
- distributed integration tests against real PostgreSQL and Redis service containers
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
```

Clients may provide an `idempotency_key`; repeated submissions return the existing persisted request.

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

The current security model remains reference-level. A real enterprise deployment would normally add OAuth/OIDC, RBAC, stronger secret/network controls, dependency scanning and policy enforcement.

## Guarded LLM enrichment

`POST /enrichment/documents` calls a configurable OpenAI-compatible endpoint, validates structured output with Pydantic and flags low-confidence results for human review. Malformed output fails closed. Included evaluation cases are synthetic and demonstrate an evaluation workflow, not production model accuracy.

## Schema migrations

Alembic is included for managed schema evolution. This replaces treating `metadata.create_all()` as the long-term production migration strategy and makes database changes reviewable and repeatable.

## CI validation

GitHub Actions validates three concerns independently:

1. Ruff quality checks plus unit tests.
2. Distributed integration against real PostgreSQL and Redis service containers.
3. Clean container image build.

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

See [`docs/decisions/`](docs/decisions/) for ADRs covering persistence, asynchronous execution, AI boundaries, integration design, LLM guardrails, security/observability and distributed state/dispatch.

See [`docs/deployment-railway.md`](docs/deployment-railway.md) for the cloud reference topology and deployment configuration.

## Roadmap

- [x] API/RPA routing boundary
- [x] persistence and append-only audit trail
- [x] asynchronous worker execution
- [x] retries, idempotency and dead-letter handling
- [x] HTTP integration layer and UiPath boundary
- [x] guarded LLM enrichment and evaluation harness
- [x] PostgreSQL state + Redis dispatch
- [x] real PostgreSQL/Redis CI integration validation
- [x] readiness, linting and container-build gates
- [x] Railway reference deployment
- [x] Alembic schema migrations
- [x] operational HTTP metrics and latency visibility
- [ ] persistent managed cloud database/storage for the reference deployment
- [ ] enterprise identity with OAuth/OIDC and RBAC
- [ ] distributed tracing with OpenTelemetry
- [ ] performance/load validation with explicit SLOs

## Scope

This repository is evidence of **automation engineering and system-design capability**: selecting integration mechanisms, separating orchestration from execution, designing for recoverability and observability, testing distributed behavior and deploying a reference topology. It does **not** replace evidence from real professional production environments and should not be used to claim Architect/Lead seniority by itself.
