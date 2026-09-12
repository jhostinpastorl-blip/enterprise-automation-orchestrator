# Enterprise Automation Orchestrator

A reference implementation for enterprise automation where one business process may need direct APIs, RPA and optional AI enrichment while still requiring durable state, retries, auditability, security controls and observable execution.

The design treats RPA as one execution mechanism inside a broader automation system rather than making the robot workflow the system of record.

## What it demonstrates

- FastAPI + Pydantic API contract
- direct HTTP integrations behind adapter boundaries
- vendor-neutral RPA gateway integration
- UiPath Orchestrator OAuth/OData job submission boundary
- SQLite for low-friction local development
- PostgreSQL-compatible durable state through SQLAlchemy
- atomic PostgreSQL worker claiming with `FOR UPDATE SKIP LOCKED`
- optional Redis-backed work dispatch
- multiple worker processes sharing one durable state store
- idempotency, bounded retries and dead-letter state
- append-only lifecycle audit events
- API-key protection, correlation IDs and structured JSON logging
- liveness and dependency-aware readiness probes
- JSON and Prometheus-style operational metrics
- optional LLM document enrichment with typed output and human-review guardrails
- repeatable LLM evaluation harness
- Docker Compose topologies for local and distributed execution
- unit tests plus PostgreSQL/Redis distributed integration tests in GitHub Actions
- automated lint and container-build validation in CI
- ADRs documenting technical decisions and trade-offs

## Architecture

```text
                         +----------------------+
                         |      API client      |
                         +----------+-----------+
                                    |
                    optional        | POST /automation-requests
                 document enrich    v
              +----------------+  +-------------------+
              | LLM boundary   |  |      FastAPI      |
              | + HITL flag    |  | auth + tracing    |
              +----------------+  +---------+---------+
                                           |
                               persist     |     publish ID
                                           v
                                 +---------+---------+
                                 |    PostgreSQL     |
                                 | state + audit     |
                                 +---------+---------+
                                           |
                                           |                 +-------------+
                                           +---------------->|    Redis    |
                                                             | dispatch    |
                                                             +------+------+ 
                                                                    |
                                                      +-------------+-------------+
                                                      |                           |
                                                      v                           v
                                             +--------+--------+         +--------+--------+
                                             |    worker A     |         |    worker B     |
                                             +---+---------+---+         +---+---------+---+
                                                 |         |                 |         |
                                            API  |         | RPA        API |         | RPA
                                                 v         v                 v         v
                                           HTTP APIs   UiPath/RPA      HTTP APIs   UiPath/RPA
```

PostgreSQL remains authoritative. Redis carries request IDs for dispatch only; workers must atomically claim the corresponding persisted request before execution. A duplicate or stale broker message therefore cannot by itself create a second execution claim.

## State and dispatch modes

The service supports two operating modes.

### Local mode

```text
AUTOMATION_DB_PATH=automation.db
DISPATCH_BACKEND=database
```

Workers poll durable state directly. SQLite keeps setup intentionally small for development and demonstrations.

### Distributed mode

```text
AUTOMATION_DATABASE_URL=postgresql+psycopg://automation:automation@postgres:5432/automation
DISPATCH_BACKEND=redis
REDIS_URL=redis://redis:6379/0
REDIS_QUEUE_NAME=automation:requests
```

The SQLAlchemy repository uses PostgreSQL row locking with `FOR UPDATE SKIP LOCKED` when multiple workers compete for eligible work. Redis provides broker-backed dispatch, while PostgreSQL continues to own lifecycle state, attempts, idempotency and audit history.

Run the distributed reference topology:

```bash
docker compose -f compose.production.yaml up --build
```

The compose file starts PostgreSQL, Redis, the API and two workers. It is a reference topology, not a claim of production hardening or cloud deployment.

## Integration layer

The worker does not simulate external execution. Adapter paths use real HTTP clients and fail explicitly when configuration is missing.

Direct API execution:

```text
TARGET_API_BASE_URL=https://api.example.internal
TARGET_API_TOKEN=...
TARGET_API_TIMEOUT_SECONDS=10
```

Vendor-neutral RPA gateway:

```text
RPA_PROVIDER=gateway
RPA_SUBMIT_URL=https://rpa-gateway.example.internal/jobs
RPA_SUBMIT_TOKEN=...
```

UiPath Orchestrator:

```text
RPA_PROVIDER=uipath
UIPATH_TOKEN_URL=https://cloud.uipath.com/identity_/connect/token
UIPATH_ORCHESTRATOR_URL=https://cloud.uipath.com/<organization>/<tenant>/orchestrator_
UIPATH_CLIENT_ID=...
UIPATH_CLIENT_SECRET=...
UIPATH_RELEASE_KEY=...
UIPATH_FOLDER_ID=...
```

The UiPath adapter obtains a client-credentials token and submits a job through the Orchestrator OData `StartJobs` surface. It is contract-tested with mocked responses; this repository does not claim a live production UiPath tenant deployment.

## Reliability model

Normal execution:

```text
queued -> running -> completed
```

Transient failure:

```text
queued -> running -> retrying -> running -> completed
```

Exhausted retry budget:

```text
queued -> running -> retrying -> ... -> dead_letter
```

Clients can provide an `idempotency_key`; repeated submissions return the existing persisted request. Redis messages are intentionally treated as dispatch hints, not authoritative state.

## Security and observability

When `ORCHESTRATOR_API_KEY` is configured, non-public endpoints require `X-API-Key`. Every HTTP request receives an `X-Correlation-ID`, and logs are emitted as structured JSON with that identifier.

Operational endpoints:

```text
GET /health
GET /ready
GET /metrics
GET /metrics/prometheus
```

`/health` confirms the API process is alive. `/ready` checks database connectivity and Redis when broker-backed dispatch is enabled, so a deployment can distinguish process liveness from dependency readiness.

The current Prometheus-style metrics intentionally remain small. A real production deployment would normally add latency histograms, dependency timing, worker throughput, retry/dead-letter counters and distributed tracing.

## Guarded document enrichment

`POST /enrichment/documents` calls a configurable OpenAI-compatible endpoint, validates structured output with Pydantic and marks low-confidence results for human review. Invalid or malformed model output fails closed rather than silently entering deterministic automation.

The included evaluation cases are synthetic and intentionally small. They demonstrate a repeatable evaluation workflow, not production model accuracy.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Run a worker in another terminal:

```bash
python -m app.worker
```

Local Docker topology:

```bash
docker compose up --build
```

Distributed reference topology:

```bash
docker compose -f compose.production.yaml up --build
```

Swagger/OpenAPI is available at `http://127.0.0.1:8000/docs`.

## CI validation

The CI pipeline separates three concerns:

- code quality and SQLite unit tests
- a distributed integration test against real PostgreSQL and Redis service containers
- a clean Docker image build

The distributed test persists a request in PostgreSQL, publishes its ID to Redis, consumes it with the worker, atomically claims it and verifies the final lifecycle and audit history. This validates the distributed path without claiming external managed-cloud scale or live RPA credentials.

## Deployment

`docs/deployment-railway.md` documents an API + worker + PostgreSQL + Redis cloud topology and the validation steps expected after deployment. A public cloud URL is intentionally not claimed until a real external deployment is connected and verified.

## Engineering decisions

See `docs/decisions/` for ADRs covering persistence, asynchronous execution, AI boundaries, integration design, LLM guardrails, security/observability and distributed state/dispatch.

## Roadmap

- [x] v0.1 - API contract and API/RPA routing boundary
- [x] v0.2 - persistence and audit trail
- [x] v0.3 - asynchronous request queue and worker
- [x] v0.4 - retry policy, idempotency and dead-letter state
- [x] v0.5 - operational metrics, containerization and CI
- [x] v0.6 - real HTTP integration layer for API and RPA execution paths
- [x] v0.7 - guarded document/LLM enrichment with typed output, human review and evaluation harness
- [x] v0.8 - API protection, correlation IDs, structured logging, Prometheus-style metrics and UiPath adapter
- [x] v0.9 - PostgreSQL-compatible state, Redis dispatch and multi-worker reference topology
- [x] v1.0 - distributed CI validation, readiness probes, linting and container-build quality gates
- [ ] cloud deployment - deploy the API/worker topology to an external provider and verify it through a public or protected URL
- [ ] enterprise identity - replace reference API-key protection with OAuth/OIDC and RBAC where the deployment context requires it
- [ ] distributed tracing - add OpenTelemetry only when a multi-service deployment provides a real trace backend

## Scope

This is a portfolio/reference project, not a claim that the implementation can be dropped unchanged into production. Its purpose is to make design decisions explicit and demonstrate how RPA, software, APIs, data infrastructure and AI can coexist inside a maintainable automation architecture.
