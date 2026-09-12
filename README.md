# Enterprise Automation Orchestrator

A reference implementation for enterprise automation where one business process may require direct APIs, RPA and optional AI enrichment while still needing durable state, retries, auditability, security controls and observable execution.

The design treats RPA as one execution mechanism inside a broader automation system rather than making the robot workflow the system of record.

## Live deployment

**API:** https://api-production-f93c7.up.railway.app

The reference topology is deployed on Railway with separate **FastAPI API, worker, PostgreSQL and Redis services**. All four services have reached Railway `SUCCESS` state. Railway deployment validation confirmed the API liveness endpoint with HTTP 200, and dependency-aware readiness was also exercised with PostgreSQL and Redis configured.

This is a portfolio/reference cloud deployment. It is not presented as evidence of enterprise production scale, load-tested availability, security certification or live production UiPath credentials.

## What it demonstrates

- FastAPI + Pydantic API contract
- direct HTTP integrations behind adapter boundaries
- vendor-neutral RPA gateway integration
- UiPath Orchestrator OAuth/OData job-submission boundary
- SQLite for low-friction local development
- PostgreSQL durable state through SQLAlchemy
- atomic PostgreSQL worker claiming with `FOR UPDATE SKIP LOCKED`
- Redis-backed work dispatch
- asynchronous workers sharing one durable state store
- idempotency, bounded retries and dead-letter state
- append-only lifecycle audit events
- API-key protection, correlation IDs and structured JSON logging
- liveness and dependency-aware readiness probes
- JSON and Prometheus-style operational metrics
- optional LLM document enrichment with typed output and human-review guardrails
- repeatable LLM evaluation harness
- Docker topologies for local/distributed execution
- unit tests plus PostgreSQL/Redis distributed integration tests in GitHub Actions
- automated lint and container-build validation in CI
- external Railway deployment
- ADRs documenting technical decisions and trade-offs

## Architecture

```text
                         +----------------------+
                         |      API client      |
                         +----------+-----------+
                                    |
                                    v
                         +----------+-----------+
                         |       FastAPI        |
                         | auth + correlation   |
                         +----------+-----------+
                                    |
                         persist    |    publish request ID
                                    v
                         +----------+-----------+
                         |      PostgreSQL      |
                         | state + audit trail  |
                         +----------+-----------+
                                    |
                                    +--------------------+
                                                         |
                                                +--------v--------+
                                                |      Redis      |
                                                |    dispatch     |
                                                +--------+--------+
                                                         |
                                              +----------+----------+
                                              |                     |
                                              v                     v
                                      +-------+-------+     +-------+-------+
                                      |    worker     |     | worker/scale  |
                                      +---+-------+---+     +---+-------+---+
                                          |       |             |       |
                                     API  |       | RPA    API |       | RPA
                                          v       v             v       v
                                      HTTP APIs  UiPath/RPA  HTTP APIs  UiPath/RPA
```

PostgreSQL remains authoritative. Redis carries request IDs for dispatch only; a worker must atomically claim the persisted request before execution. Duplicate or stale broker messages therefore cannot by themselves create a second execution claim.

## Operating modes

### Local

```text
AUTOMATION_DB_PATH=automation.db
DISPATCH_BACKEND=database
```

Workers poll durable SQLite state directly. This keeps local setup intentionally small.

### Distributed

```text
AUTOMATION_DATABASE_URL=postgresql+psycopg://...
DISPATCH_BACKEND=redis
REDIS_URL=redis://...
REDIS_QUEUE_NAME=automation:requests
```

PostgreSQL uses row locking with `FOR UPDATE SKIP LOCKED` when workers compete for eligible work. Redis provides dispatch while PostgreSQL owns lifecycle state, attempts, idempotency and audit history.

Run the local distributed topology:

```bash
docker compose -f compose.production.yaml up --build
```

## Integration layer

The worker uses explicit adapter boundaries for external execution.

**Direct API execution**

```text
TARGET_API_BASE_URL=https://api.example.internal
TARGET_API_TOKEN=...
TARGET_API_TIMEOUT_SECONDS=10
```

**Vendor-neutral RPA gateway**

```text
RPA_PROVIDER=gateway
RPA_SUBMIT_URL=https://rpa-gateway.example.internal/jobs
RPA_SUBMIT_TOKEN=...
```

**UiPath Orchestrator**

```text
RPA_PROVIDER=uipath
UIPATH_TOKEN_URL=https://cloud.uipath.com/identity_/connect/token
UIPATH_ORCHESTRATOR_URL=https://cloud.uipath.com/<organization>/<tenant>/orchestrator_
UIPATH_CLIENT_ID=...
UIPATH_CLIENT_SECRET=...
UIPATH_RELEASE_KEY=...
UIPATH_FOLDER_ID=...
```

The UiPath adapter obtains a client-credentials token and submits a job through the Orchestrator OData `StartJobs` surface. It is contract-tested with mocked HTTP responses; the repository does not claim a live production UiPath tenant integration.

## Reliability model

```text
queued -> running -> completed
queued -> running -> retrying -> running -> completed
queued -> running -> retrying -> ... -> dead_letter
```

Clients can provide an `idempotency_key`; repeated submissions return the existing persisted request. Redis messages are treated as dispatch hints, not authoritative state.

## Security and observability

When `ORCHESTRATOR_API_KEY` is configured, non-public endpoints require `X-API-Key`. HTTP requests receive an `X-Correlation-ID`, and application logs are emitted as structured JSON.

Operational endpoints:

```text
GET /health
GET /ready
GET /metrics
GET /metrics/prometheus
```

`/health` confirms process liveness. `/ready` checks database connectivity and Redis when broker-backed dispatch is enabled.

The current security control is intentionally reference-level. Enterprise deployment would normally replace the API key with OAuth/OIDC and RBAC and add stronger secrets, network and policy controls.

## Guarded LLM enrichment

`POST /enrichment/documents` calls a configurable OpenAI-compatible endpoint, validates structured output with Pydantic and marks low-confidence results for human review. Invalid or malformed model output fails closed rather than silently entering deterministic automation.

The included evaluation cases are synthetic and intentionally small. They demonstrate an evaluation workflow, not production model accuracy.

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

Swagger/OpenAPI:

```text
http://127.0.0.1:8000/docs
```

## CI validation

GitHub Actions separates three concerns:

1. Ruff quality checks plus SQLite unit tests.
2. A distributed integration test against real PostgreSQL and Redis service containers.
3. A clean container image build.

The distributed test persists a request in PostgreSQL, publishes its ID to Redis, consumes it with the worker, atomically claims it and verifies final lifecycle/audit state.

## Railway deployment

The live deployment uses:

```text
Internet -> FastAPI API -> PostgreSQL
                    |
                    +-> Redis -> Worker -> API/RPA adapter
```

See [`docs/deployment-railway.md`](docs/deployment-railway.md) for the verified deployment configuration, start commands and scope.

## Engineering decisions

See [`docs/decisions/`](docs/decisions/) for ADRs covering persistence, asynchronous execution, AI boundaries, integration design, LLM guardrails, security/observability and distributed state/dispatch.

## Roadmap

- [x] v0.1 - API contract and API/RPA routing boundary
- [x] v0.2 - persistence and audit trail
- [x] v0.3 - asynchronous request queue and worker
- [x] v0.4 - retry policy, idempotency and dead-letter state
- [x] v0.5 - operational metrics, containerization and CI
- [x] v0.6 - HTTP integration layer for API and RPA execution paths
- [x] v0.7 - guarded LLM enrichment with typed output, human review and evaluation harness
- [x] v0.8 - API protection, correlation IDs, structured logging, metrics and UiPath adapter
- [x] v0.9 - PostgreSQL state, Redis dispatch and multi-worker reference topology
- [x] v1.0 - distributed CI validation, readiness probes, linting and container-build quality gates
- [x] cloud deployment - API/worker/PostgreSQL/Redis topology deployed and validated on Railway
- [ ] enterprise identity - OAuth/OIDC and RBAC
- [ ] distributed tracing - OpenTelemetry with a real trace backend
- [ ] schema migrations - replace reference `create_all` initialization with managed migrations
- [ ] performance validation - load/concurrency testing with explicit SLOs and evidence

## Scope

This is a portfolio/reference project. It now provides evidence of designing, testing and deploying a distributed automation architecture to a managed cloud platform, but it does **not** claim enterprise production scale or replace evidence from real professional production environments.
