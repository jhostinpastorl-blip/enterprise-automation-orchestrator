# ADR 006 - Security, observability and UiPath execution boundary

## Status

Accepted for the reference implementation.

## Context

The orchestration core already separated durable state and retries from the execution adapter, but three gaps remained before the project could demonstrate a stronger production-readiness mindset:

1. external callers had no optional authentication control;
2. API requests could not be traced consistently across logs;
3. the RPA path was vendor-neutral only and did not show how an actual enterprise RPA platform could be integrated without coupling the orchestration core to it.

## Decision

### API protection

Add an optional `X-API-Key` middleware controlled by `ORCHESTRATOR_API_KEY`. When no key is configured, local/reference behavior remains unchanged. When configured, non-public endpoints require the expected key.

This is deliberately not presented as the final authentication model for a production platform. An enterprise deployment would normally prefer an identity provider, OAuth/OIDC, service identities and authorization policies.

### Correlation and logging

Every HTTP request receives a correlation ID. Caller-provided `X-Correlation-ID` values are preserved; otherwise one is generated. Application logs use JSON formatting and include the correlation ID.

The goal is to establish an observable execution boundary without tying the project to a specific log backend.

### Metrics

Keep the existing JSON metrics endpoint and add a Prometheus-style text representation. The first metrics are intentionally small: total request count and current lifecycle counts.

### UiPath integration

Keep the generic `RpaAdapter` boundary and add `UiPathOrchestratorAdapter` as one selectable provider. The adapter obtains an OAuth client-credentials token from a configurable token endpoint and starts a job through the Orchestrator OData `StartJobs` endpoint.

Provider selection is externalized through `RPA_PROVIDER`. The worker and orchestration service do not import UiPath-specific behavior directly.

## Consequences

Positive:

- platform-specific RPA integration remains isolated behind the same execution contract;
- credentials and tenant-specific URLs stay outside source control;
- requests can be correlated through structured logs;
- a deployment can enable a basic API protection control without changing application code;
- operational status can be scraped by Prometheus-compatible tooling.

Trade-offs:

- an API key is simpler than enterprise identity and RBAC;
- correlation is currently request-scoped and is not yet propagated into every external request header or persisted event;
- the UiPath adapter is contract-tested with mocked HTTP responses and does not claim a live tenant deployment;
- metrics do not yet include latency histograms, dependency timing or worker throughput.

## Next step

Move durable state and work claiming to a production database/distributed execution strategy, then add deeper telemetry and platform-specific operational metadata without changing the orchestration contract.
