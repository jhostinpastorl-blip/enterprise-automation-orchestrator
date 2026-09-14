# ADR 009: Preserve downstream throttling signals

## Status

Accepted

## Context

External APIs and automation platforms can reject work temporarily when quotas or concurrency limits are exceeded. Treating every HTTP failure identically causes avoidable retry storms and ignores useful feedback from the downstream system.

HTTP `429 Too Many Requests` can include a `Retry-After` header that tells callers when another attempt is appropriate.

## Decision

HTTP adapters detect `429` before generic status handling and raise a retryable adapter error that carries an optional `retry_after_seconds` value.

The worker uses the downstream retry hint when present. If the service does not provide a usable `Retry-After`, the configured worker retry delay remains the fallback.

This behavior applies to:

- direct API execution;
- vendor-neutral RPA gateway submission;
- UiPath token acquisition;
- UiPath job submission.

## Why

The orchestration layer should respect the capacity signal of the system it depends on. Preserving `Retry-After` is more correct than repeatedly calling a throttled dependency at a fixed arbitrary interval.

## Trade-offs

This is not full backpressure control. Multiple worker processes can still independently send traffic to the same target and exceed a shared quota.

A stronger enterprise design should add target-aware rate limiting, shared quota state, queue-depth and oldest-work-age metrics, and jittered exponential backoff for transient errors that do not provide an explicit retry time.

## Consequences

- Rate-limited requests remain inside the existing bounded retry model.
- Downstream retry instructions influence scheduling without becoming authoritative workflow state.
- The system can distinguish explicit throttling from generic integration failure.
- A future shared limiter can be added at the worker/adapter boundary without changing the external API contract.
