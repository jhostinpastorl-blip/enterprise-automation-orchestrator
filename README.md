# Enterprise Automation Orchestrator

A small reference implementation for a problem that appears often in enterprise automation: one business process may need direct APIs for some systems and RPA for others, while still requiring one place to track state, retries and audit history.

This repository is intentionally built around orchestration rather than a specific RPA vendor.

## What it demonstrates

- FastAPI contract with Pydantic validation
- API/RPA adapters behind a common execution boundary
- durable request state outside the robot workflow
- asynchronous request acceptance and worker execution
- idempotency keys for duplicate-submission protection
- bounded retries and dead-letter state
- append-only lifecycle audit events
- basic operational metrics
- Docker-based local API + worker setup
- automated tests in GitHub Actions
- architecture decisions recorded as ADRs

## Architecture

```text
                         +----------------------+
                         |      API client      |
                         +----------+-----------+
                                    |
                                    | POST /automation-requests
                                    v
+------------------+       +--------+---------+       +-------------------+
| audit / metrics  | <---- |     FastAPI      | ----> | durable request   |
+------------------+       +------------------+       | state + queue     |
                                                      +---------+---------+
                                                                |
                                                                | claim
                                                                v
                                                      +---------+---------+
                                                      | automation worker |
                                                      +----+----------+---+
                                                           |          |
                                                  API path |          | RPA path
                                                           v          v
                                                   +-------+--+   +---+---------+
                                                   | API      |   | RPA adapter |
                                                   | adapter  |   | / platform  |
                                                   +----------+   +-------------+
```

The core decision is simple: use a stable API when one exists. Use RPA when the operation is only available through a user interface or a legacy application. The orchestration layer should not force every integration into a bot workflow.

## Request lifecycle

Successful execution:

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

Every transition is appended to an audit table. The current state is stored separately so operational lookups do not have to rebuild state from the event history.

## Idempotency

Clients can send an `idempotency_key`. Submitting the same key again returns the existing request instead of creating another unit of work. This is useful when a caller times out and cannot know whether its previous submission was accepted.

## Run locally

### Python

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Run the worker in another terminal:

```bash
python -m app.worker
```

### Docker Compose

```bash
docker compose up --build
```

Swagger/OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

## Example

Submit work:

```bash
curl -X POST http://127.0.0.1:8000/automation-requests \
  -H "Content-Type: application/json" \
  -d '{
    "process":"customer_update",
    "target":"crm",
    "execution_channel":"api",
    "payload":{"customer_id":"C-10042"},
    "idempotency_key":"customer-C-10042-update"
  }'
```

The API returns `202 Accepted` with a request ID and `queued` status. The worker later changes that state as it processes the request.

Operational endpoints:

```text
GET /health
GET /automation-requests/{request_id}
GET /automation-requests/{request_id}/audit
GET /metrics
```

## Why SQLite here?

SQLite keeps the repository runnable with almost no infrastructure and is enough to demonstrate durable state, audit history and asynchronous processing locally.

It is not presented as the final choice for a high-throughput distributed automation platform. A production design with multiple workers would normally move durable state to a production database and work dispatch to a queue/broker with atomic distributed consumption semantics.

That boundary is deliberate: the API and worker depend on repository and adapter contracts rather than embedding SQL or vendor-specific RPA calls throughout the workflow.

## Where AI fits

AI is not added merely to label the project as "AI automation". The deterministic orchestration path should stay deterministic.

A sensible extension would place document classification or unstructured-field extraction before routing, with structured outputs, confidence thresholds and human review for uncertain results. The execution, retry, idempotency and audit layers would remain the same.

## Engineering decisions

See `docs/decisions/` for short ADRs explaining the reasoning behind persistence and asynchronous execution.

## Roadmap

- [x] v0.1 - API contract and API/RPA routing boundary
- [x] v0.2 - persistence and audit trail
- [x] v0.3 - asynchronous request queue and worker
- [x] v0.4 - retry policy, idempotency and dead-letter state
- [x] v0.5 - operational metrics, containerization and CI
- [ ] v0.6 - evaluated document/LLM enrichment with structured output and human review

## Scope

This is a portfolio/reference project, not a claim that this implementation should be dropped unchanged into production. Its purpose is to make design decisions explicit and to show how RPA can be one component inside a broader automation architecture.
