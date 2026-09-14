# ADR 008: Dead-letter replay preserves the logical request

## Status

Accepted

## Context

Bounded retries eventually move a request to `dead_letter`. Operators need a controlled recovery path after correcting transient infrastructure, credentials, downstream availability or bad configuration.

A replay mechanism must not silently erase the failure history or create duplicate logical work that is difficult to correlate.

## Decision

Expose an explicit replay operation for dead-letter work:

```text
POST /automation-requests/{request_id}/replay
```

The operation is valid only when the current status is `dead_letter`.

Replay:

1. locks and re-validates the persisted request;
2. returns the same logical request to `queued`;
3. resets the execution-attempt budget;
4. records a new append-only audit event describing the operator replay;
5. republishes the request ID when broker-backed dispatch is enabled.

The original `request_id` is preserved.

## Why

Keeping the same logical request ID gives operators one continuous audit history from initial submission through failure, dead letter, replay and eventual completion. It also avoids manufacturing a second business request solely because execution had to be recovered.

## Trade-offs

Resetting `attempt_count` makes that field represent the current replay cycle rather than lifetime execution attempts. Lifetime history remains reconstructable from audit events, but a larger production system may want a separate first-class `execution_attempts` or `replay_cycles` table.

This reference implementation also does not yet capture actor identity or a mandatory replay reason. With enterprise RBAC, replay should record who authorized it and why.

## Consequences

- Recovery is explicit rather than automatic after retry exhaustion.
- Replaying non-dead-letter work returns a conflict instead of changing state.
- The audit trail remains continuous and append-only.
- Broker dispatch remains secondary to persisted state; workers must still claim the replayed row before execution.
