# ADR 001: Persist orchestration state outside RPA workflows

## Status

Accepted

## Context

Automation requests need to remain traceable even when execution happens in different channels. An API integration can return quickly, while an RPA run may depend on a desktop session, external application availability or a longer-running robot job.

Keeping state only inside the bot workflow would make request tracking dependent on the automation platform and would complicate support, reporting and future retries.

## Decision

The orchestrator owns request state and lifecycle history.

For the current iteration:

- `automation_requests` stores the latest known state of each request;
- `automation_events` stores an append-only history of lifecycle transitions;
- the request is persisted as `accepted` before an execution adapter is invoked;
- the final state is recorded as `completed` or `failed`;
- SQLite is used for local development behind a repository boundary.

## Why SQLite now

The current goal is to validate the persistence model and service boundary, not database scale. SQLite keeps the project easy to run locally and avoids adding infrastructure before it is needed.

A production deployment with concurrent workers would likely move to PostgreSQL or another managed relational database. The repository boundary is intended to make that change local to the persistence layer.

## Consequences

Positive:

- request history survives beyond an individual bot run;
- API and RPA execution share the same operational model;
- support teams can query current state without opening the RPA platform;
- later retry and idempotency rules have a durable source of truth.

Trade-offs:

- the current implementation is synchronous;
- SQLite is not the intended database for horizontally scaled workers;
- schema migrations are not yet introduced because the data model is still small and evolving.

## Next step

Introduce a queue and worker so request acceptance is separated from execution. That will make the persisted `accepted` state meaningful for long-running work and prepare the project for retry and dead-letter handling.
