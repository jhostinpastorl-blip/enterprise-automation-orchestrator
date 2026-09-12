# ADR 004: Keep external integrations behind adapters

## Status

Accepted

## Context

Enterprise automation frequently mixes modern systems that expose HTTP APIs with legacy applications that still require RPA. If vendor-specific calls, credentials and transport details leak into the orchestration core, the worker becomes difficult to test, replace and operate.

## Decision

Keep execution behind the existing `AutomationAdapter` boundary.

The API path performs a real HTTP POST to a configurable target base URL. The RPA path submits a vendor-neutral job contract to an external RPA platform or gateway through HTTP. The orchestrator owns request state, retry policy and audit history; the adapter owns transport-specific execution details.

Runtime endpoints and tokens are supplied through environment variables. Secrets are not stored in source code or written to logs.

The current RPA adapter intentionally does not claim a native UiPath or Automation Anywhere integration. A production implementation can replace this adapter with a platform-specific client without changing the orchestration lifecycle.

## Consequences

- API and RPA execution can evolve independently from orchestration state management.
- HTTP behavior is testable with mock transports without requiring external systems.
- Missing integration configuration fails explicitly instead of silently simulating success.
- The reference project demonstrates a real integration boundary while remaining vendor-neutral.
- Platform-specific authentication, callbacks and job-status polling remain future extensions.
