# Railway deployment topology

This repository can be deployed as separate API and worker services backed by managed PostgreSQL and Redis. The deployment keeps the same boundaries used by the local distributed topology.

## Services

Create four Railway resources in one project:

1. PostgreSQL database
2. Redis database
3. API service from this GitHub repository
4. Worker service from this GitHub repository

The API and worker use the same image and environment configuration but different start commands.

## API service

Build from the repository Dockerfile.

Start command:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Required runtime variables:

```text
AUTOMATION_DATABASE_URL=<Railway PostgreSQL SQLAlchemy URL>
DISPATCH_BACKEND=redis
REDIS_URL=<Railway Redis URL>
REDIS_QUEUE_NAME=automation:requests
LOG_LEVEL=INFO
ORCHESTRATOR_API_KEY=<generated secret>
```

Health endpoint:

```text
/health
```

Readiness endpoint:

```text
/ready
```

`/ready` checks the configured database and, when Redis dispatch is enabled, Redis connectivity.

## Worker service

Build from the same repository Dockerfile.

Start command:

```text
python -m app.worker
```

Use the same PostgreSQL and Redis variables as the API. Add:

```text
RETRY_DELAY_SECONDS=5
WORKER_POLL_INTERVAL_SECONDS=1
```

Scale worker replicas only after validating downstream system idempotency and concurrency behavior.

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

The UiPath path requires the documented `UIPATH_*` variables. Secrets must be configured through the platform secret store and never committed to Git.

## Deployment validation

After deployment:

1. Verify `GET /health` returns HTTP 200.
2. Verify `GET /ready` reports PostgreSQL and Redis as `ok`.
3. Submit one request with a unique `idempotency_key`.
4. Confirm a worker moves it from `queued` to `running` and then to its terminal state.
5. Re-submit the same idempotency key and confirm the existing request is returned.
6. Review structured logs using the returned `X-Correlation-ID`.
7. Check `/metrics/prometheus` for lifecycle counts.

## Scope

A live Railway deployment would demonstrate deployment and operations of this reference implementation. It would not by itself prove enterprise production scale, availability targets, security certification, or live UiPath production integration. Those claims require separate evidence.
