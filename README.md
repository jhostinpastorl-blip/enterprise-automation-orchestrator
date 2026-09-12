# Enterprise Automation Orchestrator

A reference implementation for orchestrating enterprise automation workloads across APIs and RPA.

The project focuses on a common integration problem: some target systems expose stable APIs, while others can only be automated through their user interface. The orchestrator keeps that decision outside the business workflow and routes each request through the appropriate adapter.

## Current scope

The first iteration provides:

- a small FastAPI service for receiving automation requests;
- typed request validation with Pydantic;
- a service layer that owns routing decisions;
- separate API and RPA adapters behind a common interface;
- explicit request states that can later be persisted and processed asynchronously.

## Architecture

```text
Client
  |
  v
FastAPI endpoint
  |
  v
Automation service
  |
  +--> API adapter ----> target system API
  |
  +--> RPA adapter ----> robot / UI automation
```

The rule is intentionally simple: use an API when a reliable one is available; use RPA when the business operation depends on a UI-only system. This keeps RPA as one execution channel rather than making the workflow itself dependent on a specific automation platform.

## Why this project exists

Enterprise automation often becomes difficult to maintain when validation, orchestration, integration logic and UI automation are all placed inside the same bot workflow. This project explores a cleaner boundary between those concerns.

The next iterations will add persistence, queue-based processing, idempotency, retry policies, structured logging and operational visibility before introducing any AI capability.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the generated API documentation.

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

## Roadmap

- v0.1 - API contract and routing boundary
- v0.2 - persistence and audit trail
- v0.3 - asynchronous queue and worker
- v0.4 - retry, idempotency and dead-letter handling
- v0.5 - observability and operational metrics
- v0.6 - optional document/LLM enrichment where it provides a clear business benefit

## Status

Early-stage portfolio project. The goal is to evolve it incrementally and document the design decisions as the architecture grows.
