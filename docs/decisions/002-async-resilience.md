# ADR 002: Separate request acceptance from execution

## Status

Accepted.

## Context

Synchronous execution couples API response time to target-system latency and to the availability of RPA workers. That becomes fragile when an automation takes minutes, a target system is temporarily unavailable, or a robot session needs to be recovered.

## Decision

The API persists an automation request and returns `202 Accepted`. A worker claims queued work and executes the selected adapter independently.

The persisted lifecycle is:

`queued -> running -> completed`

Failures use:

`running -> retrying -> running -> ... -> dead_letter`

An optional idempotency key prevents duplicate submissions from creating duplicate work.

## Retry policy

Retries are bounded by `max_attempts`. Failed requests are delayed before they become eligible again. Once the attempt budget is exhausted, the request moves to `dead_letter` and requires an explicit operational decision rather than retrying forever.

## Trade-offs

SQLite is retained for the portfolio/local-development stage. It gives a compact way to demonstrate durable state, auditability and worker separation without requiring infrastructure to run the project.

This implementation intentionally assumes a small number of local workers. For production-scale concurrency, the queue boundary should move to infrastructure designed for distributed consumers, such as a managed queue or broker, and persistence should move to PostgreSQL or another production database.

## Consequences

- API latency is decoupled from automation execution time.
- Request state survives API restarts.
- Transient failures can be retried without client resubmission.
- Duplicate client submissions can be made safe with idempotency keys.
- Operational teams can identify requests that have exhausted retries.
