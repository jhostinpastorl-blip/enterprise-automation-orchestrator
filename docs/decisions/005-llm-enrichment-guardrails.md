# ADR 005: Keep LLM enrichment outside deterministic orchestration

## Status

Accepted

## Context

Some enterprise automation requests begin with unstructured documents or free text. An LLM can help classify the document and extract candidate fields, but model output is probabilistic and should not silently become trusted orchestration state.

## Decision

Expose document enrichment as a separate pre-processing boundary.

The enrichment component:

- calls a configurable OpenAI-compatible endpoint;
- requires JSON output and validates it with Pydantic;
- records provider/model metadata in the returned result;
- applies a configurable confidence threshold;
- marks low-confidence results for human review;
- fails closed when configuration or output validation is invalid.

The deterministic automation queue, retries, idempotency and audit lifecycle remain independent from the LLM call.

An evaluation harness and a small synthetic case set are included so model/provider changes can be measured instead of accepted by intuition. The repository does not claim production accuracy from that sample set.

## Consequences

- AI can be added where ambiguity exists without making the orchestration core probabilistic.
- Low-confidence output has an explicit human-in-the-loop path.
- Provider/model changes can be evaluated with the same cases.
- Secrets stay in runtime configuration rather than source code.
- Production use would still require a representative evaluation dataset, privacy controls, cost/latency monitoring and provider-specific security review.
