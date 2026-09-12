# Architecture walkthrough

## Problem

Enterprise automation rarely lives in one technology. A process may have a stable API for one system and only a graphical interface for another. Long-running execution, transient failures and retries also make a synchronous bot-centric design difficult to operate.

## Boundaries

The API accepts and validates requests. It does not execute the automation inline.

The repository owns durable lifecycle state and audit history.

The worker owns execution. It claims eligible work, selects the adapter and records the result.

Adapters isolate integration technology. An API adapter can call a service directly; an RPA adapter can hand work to a robot platform without putting platform-specific details into orchestration code.

## Reliability choices

### Idempotency

A caller may retry a submission after a timeout. An idempotency key prevents that network uncertainty from creating duplicate work.

### Retry budget

Retries are bounded. Permanent failures should not consume workers forever. Exhausted requests move to `dead_letter` so an operator can decide whether to correct data, change configuration or replay work.

### Audit history

Current state and event history are stored separately. Current state keeps operational reads simple; events retain the sequence of lifecycle transitions.

### Atomic local claims

SQLite queue claims use an immediate transaction so two local workers cannot select the same pending row before its state changes to `running`.

## Production evolution

This repository favors low setup cost over production-scale infrastructure. A larger deployment would normally introduce:

1. PostgreSQL or another production datastore for request state.
2. A managed queue or broker for distributed work delivery.
3. Platform-specific adapters for UiPath, Automation Anywhere or other execution engines.
4. Authentication/authorization and secrets management.
5. Distributed traces, structured logs and metrics exported to an observability platform.
6. Explicit replay tooling for dead-letter work.
7. Horizontal worker scaling and rate limits per downstream system.

## AI extension

LLM-based classification or extraction should be an enrichment stage, not part of the queue/retry state machine. The model should return validated structured output and uncertain cases should route to human review. This keeps deterministic operational behavior independent from model variability.
