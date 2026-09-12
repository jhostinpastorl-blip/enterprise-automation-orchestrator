# Enterprise Automation Orchestrator

A reference implementation for orchestrating enterprise automation workloads across APIs and RPA.

The project focuses on a common integration problem: some target systems expose stable APIs, while others can only be automated through their user interface. The orchestrator keeps that decision outside the business workflow and routes each request through the appropriate adapter.

## Current scope

Version 0.2 provides:

- a FastAPI service for receiving automation requests;
- typed request validation with Pydantic;
- a service layer that owns routing decisions;
- separate API and RPA adapters behind a common interface;
- SQLite persistence for request state;
- an append-only audit event table for lifecycle changes;
- request lookup by ID for operational traceability.

## Architecture

```text
Client
  |
  v
FastAPI endpoint
  |
  v
Automation service ---------> SQLite request state
  |                               |
  |                               +--> audit events
  |
  +--> API adapter ----> target system API
  |
  +--> RPA adapter ----> robot / UI automation
```

The rule is intentionally simple: use an API when a reliable one is available; use RPA when the business operation depends on a UI-only system. This keeps RPA as one execution channel rather than making the workflow itself dependent on a specific automation platform.

## Persistence and audit trail

Each request is persisted before execution with an `accepted` status. The final state is then written as either `completed` or `failed`.

The current state lives in `automation_requests`, while every lifecycle transition is also appended to `automation_events`. Keeping current state and history separate makes operational queries simple without losing the execution trail.

SQLite is deliberate at this stage: it keeps local development lightweight while the repository boundary leaves room to move to PostgreSQL in a later iteration without pushing database logic into the API layer.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the generated API documentation.

The database defaults to `automation.db`. To use another path:

```bash
export AUTOMATION_DB_PATH=/tmp/automation.db
```

## Example request

```json
{
  "process": "customer_update",
  "target": "crm",
  "execution_channel": "api",
  "payload": {
    "customer_id": "C-10042",
    "email": "customer@example.com"
  }
}
```

Create a request:

```bash
curl -X POST http://127.0.0.1:8000/automation-requests \
  -H "Content-Type: application/json" \
  -d '{"process":"customer_update","target":"crm","execution_channel":"api","payload":{"customer_id":"C-10042"}}'
```

Retrieve its persisted state:

```bash
curl http://127.0.0.1:8000/automation-requests/<request_id>
```

## Design principles

- Prefer direct API integration when a stable contract exists.
- Isolate RPA behind an adapter when UI automation is unavoidable.
- Persist request state outside the bot workflow.
- Keep an audit trail of state transitions.
- Add asynchronous processing before increasing execution complexity.
- Introduce AI only where it solves an uncertain or unstructured task better than deterministic logic.

## Roadmap

- [x] v0.1 - API contract and routing boundary
- [x] v0.2 - persistence and audit trail
- [ ] v0.3 - asynchronous queue and worker
- [ ] v0.4 - retry, idempotency and dead-letter handling
- [ ] v0.5 - observability and operational metrics
- [ ] v0.6 - optional document/LLM enrichment where it provides a clear business benefit

## Status

This is an evolving portfolio project focused on design decisions found in real enterprise automation environments. Features are introduced incrementally so each architectural change has a clear reason and trade-off.
