# ADR 003: Keep deterministic orchestration separate from AI enrichment

## Status

Accepted as the next extension boundary.

## Context

Not every automation problem benefits from an LLM. Routing, retries, idempotency and execution-state transitions should remain deterministic and testable.

AI becomes useful when an input is unstructured or ambiguous, for example classifying a free-form document, extracting fields that do not follow a stable template, or recommending the next action from natural-language content.

## Decision

Any future LLM capability will sit before execution as an enrichment step. It must return a validated structured result instead of free-form text to the orchestration layer.

The enrichment contract should include:

- a typed output schema;
- confidence or validation signals;
- a human-review path for uncertain results;
- provider/model metadata for auditability;
- latency and cost measurements;
- a small evaluation dataset before enabling automated decisions.

The worker, retry policy and API/RPA adapters remain independent of the model provider.

## Why it is not implemented yet

Adding an LLM call without an evaluated business case would create a misleading demo rather than evidence of good automation engineering. The repository first establishes the deterministic platform needed to operate an AI-assisted step safely.

A future iteration can add document enrichment once an actual extraction/classification use case and evaluation set are defined.
