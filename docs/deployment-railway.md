# Railway deployment topology

This reference implementation is deployed on Railway as separate API and worker services backed by PostgreSQL and Redis.

## Verified deployment

Public API:

```text
https://api-production-f93c7.up.railway.app
```

Verified Railway services:

1. `api` — FastAPI service from this GitHub repository
2. `worker` — asynchronous worker from the same repository
3. `postgres` — PostgreSQL 16
4. `redis` — Redis 7

The deployed API, worker, PostgreSQL and Redis services have all reached Railway `SUCCESS` state. Railway health validation has confirmed `GET /health` returns HTTP 200. A dependency-aware `/ready` healthcheck also completed successfully during deployment validation with PostgreSQL and Redis configured.

## API service

Build from the repository Dockerfile.

Start command:

```text
sh -c 'python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"'
```

Runtime variables:

```text
AUTOMATION_DATABASE_URL=<Railway PostgreSQL SQLAlchemy URL>
DISPATCH_BACKEND=redis
REDIS_URL=<Railway Redis private URL>
REDIS_QUEUE_NAME=automation:requests
LOG_LEVEL=INFO
PORT=8000
```

Liveness endpoint:

```text
GET /health
```

Dependency-aware readiness endpoint:

```text
GET /ready
```

`/ready` executes a database connectivity check and pings Redis when broker-backed dispatch is enabled.

## Worker service

The worker uses the same application source and PostgreSQL/Redis configuration. The deployment initializes the reference schema before starting the worker:

```text
python -c "from app.database import init_database; init_database()" && python -m app.worker
```

This keeps PostgreSQL authoritative for lifecycle state and audit history while Redis carries request IDs for dispatch.

## External integrations

Direct API execution requires:

```text
TARGET_API_BASE_URL=
TARGET_API_TOKEN=
TARGET_API_TIMEOUT_SECONDS=10
```

The generic RPA gateway path requires:

```text
RPA_PROVIDER=gateway
RPA_SUBMIT_URL=
RPA_SUBMIT_TOKEN=
```

The UiPath path requires the documented `UIPATH_*` variables. The current portfolio deployment does not claim live production UiPath credentials.

## Validation completed

- GitHub Actions unit/quality tests: passed
- GitHub Actions PostgreSQL + Redis distributed integration test: passed
- GitHub Actions container build: passed
- Railway PostgreSQL service: `SUCCESS`
- Railway Redis service: `SUCCESS`
- Railway worker service: `SUCCESS`
- Railway API service: `SUCCESS`
- Railway `/health`: HTTP 200 during deployment healthcheck
- Railway dependency-aware `/ready`: successfully passed during deployment validation
- Public Railway domain generated and attached to the API service

## Scope

This deployment demonstrates that the reference architecture can be built and operated on an external managed cloud platform with separate API, worker, PostgreSQL and Redis services. It does **not** by itself prove enterprise production scale, load-tested availability, security certification, live production UiPath integration, enterprise OAuth/OIDC/RBAC, or production AI model performance. Those claims require separate evidence.
