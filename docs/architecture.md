# Architecture walkthrough

## Problem

Enterprise automation rarely lives in one technology. A process may have a stable API for one system, only a graphical interface for another, and an AI enrichment step for unstructured data. Long-running execution, transient failures and retries make a synchronous bot-centric design difficult to operate, recover and audit.

The orchestrator therefore treats RPA as one execution mechanism rather than the system of record.

## Current reference architecture

```text
Client
  |
  v
FastAPI --------------------------> PostgreSQL
  |                                state + audit
  | publish request ID                 ^
  v                                    |
Redis ----------------------------> Worker
                                      |  |
                                      |  +--> RPA / UiPath boundary
                                      +-----> Direct HTTP API

Optional AI enrichment is exposed as a guarded service boundary and does not own
queue state or retry semantics.
```

### Responsibilities

**FastAPI** accepts requests, validates contracts, exposes operational endpoints and returns persisted lifecycle state. It does not run long-lived automation inline.

**PostgreSQL** is authoritative for request lifecycle state and append-only audit events in distributed mode. SQLite remains available for low-friction local development.

**Redis** is a dispatch accelerator. It transports request IDs but is not the authoritative queue state. If a broker message is stale or lost, workers fall back to persisted eligible work.

**Worker** claims eligible work atomically, selects the requested execution adapter, executes it and records completion, retry or dead-letter state.

**Adapters** isolate integration technology. A stable supported API is preferred when available; an RPA boundary is used when UI automation is the appropriate mechanism. Vendor-specific details remain outside orchestration logic.

## Reliability model

### Idempotent submission

A caller may retry a submission after a timeout. An idempotency key prevents network uncertainty from creating duplicate logical work.

### Atomic claims

PostgreSQL workers use row locking with `FOR UPDATE SKIP LOCKED` so horizontally scaled workers can claim separate eligible rows without serializing the entire queue. SQLite local mode uses an immediate transaction for equivalent single-database protection.

### Bounded retries and dead letter

Retries are deliberately finite. Permanent failures should not consume worker capacity forever. Exhausted work moves to `dead_letter` and requires an explicit operator replay.

### Auditable replay

`POST /automation-requests/{request_id}/replay` only accepts requests currently in `dead_letter`. Replay returns the same logical request to `queued`, resets its attempt budget and appends a new lifecycle event. Reusing the same request ID preserves continuity of the audit trail while making the operator action visible.

This is a conscious trade-off: the current reference model optimizes for a single logical request history. A stricter enterprise implementation could model execution attempts or replays as separate first-class entities linked to the original request.

### Broker recovery

Redis dispatch does not make delivery authoritative. After consuming an ID the worker must still claim the persisted request. If the message is stale, duplicate or missing, durable state determines whether work is eligible.

## Observability

The reference implementation currently includes:

- correlation IDs propagated through HTTP responses and structured logs;
- liveness and dependency-aware readiness probes;
- lifecycle status metrics;
- HTTP request count and latency observations;
- append-only lifecycle audit events.

The next observability step is distributed tracing with OpenTelemetry so one execution can be followed across API admission, persistence, dispatch, worker claim and downstream adapter calls.

## Security boundary

The current reference deployment supports API-key protection for non-public endpoints and keeps configuration outside source control. This is intentionally not presented as enterprise identity.

A production enterprise deployment would normally add OAuth/OIDC, RBAC, managed secrets, private networking where appropriate, dependency/image scanning and policy enforcement.

## AI boundary

LLM-based classification or extraction is treated as enrichment, not as the owner of deterministic workflow state. Model output is validated as structured data; malformed output fails closed and low-confidence results can require human review.

This separation keeps queue/retry behavior deterministic even when model behavior is probabilistic.

## Current limitations and deliberate next steps

The project already demonstrates PostgreSQL-backed durable state, Redis dispatch, distributed worker claims, API/RPA integration boundaries, guarded LLM enrichment, CI validation and a Railway reference deployment.

The remaining work is intentionally focused on operational depth rather than adding technologies for appearance:

1. Per-target rate limiting and backpressure, including explicit handling for `429` and `Retry-After`.
2. Exponential backoff with jitter to reduce synchronized retry storms.
3. OpenTelemetry traces across request admission, queueing, worker execution and downstream calls.
4. Load/performance validation with documented concurrency, throughput and p50/p95/p99 latency.
5. Explicit SLOs and saturation signals such as queue depth and oldest-work age.
6. Enterprise identity/authorization and stronger secrets/network controls.
7. Persistent managed cloud storage for the public reference deployment.

## Design principle

The repository is intentionally opinionated about one point: **orchestration state must survive outside the robot**. RPA, APIs and AI can all participate in the same business process, but reliability, recoverability and auditability belong to the orchestration layer rather than an individual execution technology.
