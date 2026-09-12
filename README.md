# Enterprise Automation Orchestrator

A small reference implementation for a problem that appears often in enterprise automation: one business process may need direct APIs for some systems and RPA for others, while still requiring one place to track state, retries and audit history.

This repository is intentionally built around orchestration rather than a specific RPA vendor.

## What it demonstrates

- FastAPI contract with Pydantic validation
- real HTTP API execution behind an adapter boundary
- vendor-neutral HTTP submission to an external RPA platform/gateway
- durable request state outside the robot workflow
- asynchronous request acceptance and worker execution
- idempotency keys for duplicate-submission protection
- bounded retries and dead-letter state
- append-only lifecycle audit events
- basic operational metrics
- optional LLM document enrichment with typed output and human-review guardrails
- repeatable enrichment evaluation harness
- Docker-based local API + worker setup
- automated tests in GitHub Actions
- architecture decisions recorded as ADRs

## Architecture

```text
                         +----------------------+
                         |      API client      |
                         +----------+-----------+
                                    |
                    optional        | POST /automation-requests
                 document enrich    v
              +----------------+  +--------+---------+       +-------------------+
              | LLM boundary   |  |     FastAPI      | ----> | durable request   |
              | + HITL flag    |  +------------------+       | state + queue     |
              +----------------+                              +---------+---------+
                                                                      |
                                                                      | claim
                                                                      v
                                                            +---------+---------+
                                                            | automation worker |
                                                            +----+----------+---+
                                                                 |          |
                                                        API path |          | RPA path
                                                                 v          v
                                                         +-------+--+   +---+----------------+
                                                         | HTTP API |   | RPA platform /     |
                                                         | adapter  |   | gateway adapter    |
                                                         +----------+   +--------------------+
```

The core decision is simple: use a stable API when one exists. Use RPA when the operation is only available through a user interface or a legacy application. Keep probabilistic AI enrichment outside the deterministic orchestration lifecycle.

## Integration layer

The worker does not simulate API/RPA success. Both execution paths use real HTTP clients and fail explicitly when integration configuration is missing.

For direct API execution:

```text
TARGET_API_BASE_URL=https://api.example.internal
TARGET_API_TOKEN=...
TARGET_API_TIMEOUT_SECONDS=10
```

For RPA execution:

```text
RPA_SUBMIT_URL=https://rpa-gateway.example.internal/jobs
RPA_SUBMIT_TOKEN=...
RPA_SUBMIT_TIMEOUT_SECONDS=10
```

The RPA path submits a vendor-neutral job contract. A production implementation can replace this adapter with a native UiPath or Automation Anywhere client without changing the orchestration lifecycle.

This repository does **not** claim that a native vendor integration is already implemented.

## Guarded document enrichment

`POST /enrichment/documents` sends unstructured text to a configurable OpenAI-compatible endpoint and validates the returned JSON into a typed model.

Expected output fields:

```text
document_type
extracted_fields
confidence
requires_human_review
provider
model
```

Low-confidence output is marked for human review using the request's `review_threshold`. Invalid JSON, invalid confidence values, HTTP failures or missing configuration fail closed instead of silently passing bad model output into automation.

Runtime configuration:

```text
LLM_BASE_URL=https://llm-provider.example/v1
LLM_API_KEY=...
LLM_MODEL=your-model
LLM_TIMEOUT_SECONDS=20
```

The repository includes `evaluation/document_cases.json` and `scripts/evaluate_enrichment.py` so provider/model changes can be measured using the same case set. The included sample is synthetic and intentionally small; it is an evaluation harness, not a claim of production model accuracy.

## Request lifecycle

```text
queued -> running -> completed
```

Transient failures can move through `retrying`; exhausted retry budgets move to `dead_letter`. Every transition is appended to an audit table.

## Idempotency

Clients can send an `idempotency_key`. Re-submitting the same key returns the existing request instead of creating another unit of work.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Run the worker separately after configuring the integration variables you want to exercise:

```bash
python -m app.worker
```

Run the optional LLM evaluation only when an endpoint/model is configured:

```bash
python scripts/evaluate_enrichment.py
```

Docker Compose:

```bash
docker compose up --build
```

Swagger/OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

Operational endpoints:

```text
GET /health
POST /automation-requests
POST /enrichment/documents
GET /automation-requests/{request_id}
GET /automation-requests/{request_id}/audit
GET /metrics
```

## Why SQLite here?

SQLite keeps the repository runnable with almost no infrastructure and is enough to demonstrate durable state, audit history and asynchronous processing locally.

It is not presented as the final choice for a high-throughput distributed automation platform. A production design with multiple workers would normally move durable state to a production database and dispatch work through a queue/broker with distributed consumption semantics.

## Engineering decisions

See `docs/decisions/` for ADRs covering persistence, asynchronous execution, AI boundaries, external integration design and LLM guardrails.

## Roadmap

- [x] v0.1 - API contract and API/RPA routing boundary
- [x] v0.2 - persistence and audit trail
- [x] v0.3 - asynchronous request queue and worker
- [x] v0.4 - retry policy, idempotency and dead-letter state
- [x] v0.5 - operational metrics, containerization and CI
- [x] v0.6 - real HTTP integration layer for API and RPA execution paths
- [x] v0.7 - guarded document/LLM enrichment with typed output, human review and evaluation harness
- [ ] v0.8 - production database/queue adapter and distributed worker strategy

## Scope

This is a portfolio/reference project, not a claim that this implementation should be dropped unchanged into production. Its purpose is to make design decisions explicit and to show how RPA, software, APIs and AI can coexist inside a broader automation architecture without pretending every component has the same reliability characteristics.
