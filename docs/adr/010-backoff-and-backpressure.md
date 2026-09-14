# ADR 010: Exponential backoff, jitter and downstream backpressure

## Status
Accepted

## Context
Enterprise targets can fail transiently or throttle callers. Retrying every failed request at a fixed interval can synchronize workers and create retry storms. A downstream `Retry-After` response also signals that new work for the same target should not immediately be sent again.

## Decision
When a downstream explicitly returns `Retry-After`, that value takes precedence over local retry policy. The worker also places that target into a local cooldown so subsequent work observed by the same worker is deferred.

For transient failures without an explicit server hint, retries use exponential backoff with bounded positive jitter. `MAX_RETRY_DELAY_SECONDS` caps growth and `RETRY_JITTER_RATIO` controls jitter.

## Consequences
This reduces synchronized retry pressure and makes downstream throttling an explicit orchestration concern. The current cooldown is worker-local, so it is intentionally not described as distributed global rate limiting.

A multi-worker production deployment that requires a shared per-target quota should move cooldown/rate state to Redis or a dedicated distributed rate limiter. That is a separate scaling decision rather than hidden in the adapter.
