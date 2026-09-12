# ADR 007 - PostgreSQL state and Redis dispatch

## Status

Accepted for the reference implementation.

## Context

The original implementation used SQLite as both durable state and work queue. That keeps local setup simple, but it does not model how multiple worker processes safely compete for work in a distributed deployment.

The orchestration layer also needs to distinguish between two concerns:

- durable business/execution state that must survive process or broker failures;
- fast dispatch that tells workers which persisted request is ready to execute.

Treating the broker as the system of record would make lifecycle recovery and audit behavior harder to reason about.

## Decision

### Durable state

Use SQLAlchemy as the persistence boundary. Local development continues to use SQLite by default. When `AUTOMATION_DATABASE_URL` points to PostgreSQL, the same repository persists requests and audit events there.

For PostgreSQL workers, eligible rows are selected with `FOR UPDATE SKIP LOCKED`. This lets concurrent workers claim different requests without waiting on the same row lock.

### Dispatch

Add a `DispatchQueue` abstraction with two implementations:

- `DatabaseDispatchQueue`: no external broker; workers claim the next eligible persisted row.
- `RedisDispatchQueue`: API submission persists the request first, then publishes only the request ID to Redis.

A brokered worker consumes the ID and must successfully claim that persisted request before execution. Stale or duplicate Redis messages are therefore safe to discard when the database row is no longer eligible.

### Source of truth

PostgreSQL/SQLite owns:

- lifecycle status;
- attempt count;
- retry schedule;
- idempotency key;
- request payload;
- append-only audit events.

Redis owns no business state. It is a dispatch mechanism only.

## Consequences

Positive:

- SQLite remains available for simple local development;
- PostgreSQL supports multiple workers with database-level row locking;
- Redis reduces database polling in the distributed topology;
- broker messages can be duplicated or become stale without automatically creating duplicate execution;
- workers remain independent from RPA/API vendor implementations.

Trade-offs:

- Redis list dispatch is intentionally simpler than a managed enterprise broker;
- the reference topology does not yet implement broker acknowledgement/redelivery semantics comparable to RabbitMQ, Azure Service Bus or SQS visibility timeouts;
- PostgreSQL migrations are still lightweight and would normally be managed with a migration tool such as Alembic in a production service;
- distributed tracing is not yet propagated end-to-end through every external dependency.

## Operational topology

`compose.production.yaml` starts PostgreSQL, Redis, the API and two workers. It exists to make the concurrency and infrastructure boundaries executable locally; it is not presented as a cloud production deployment.

## Next step

A production-oriented v1.0 should add stronger identity/RBAC, schema migrations, deeper telemetry, cloud-managed infrastructure and a deployment pipeline while preserving the same state/dispatch separation.
