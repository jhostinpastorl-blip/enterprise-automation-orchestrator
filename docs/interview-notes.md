# Design defense notes

These notes are for reviewing the project before an interview. They are not a script.

## Why not put everything in RPA?

UI automation is appropriate when a system has no usable integration contract. API calls, persistence, retry policy and orchestration are easier to test and maintain in code, so they stay outside the robot workflow.

## Why return 202 instead of waiting for execution?

Automation jobs can be slow or temporarily blocked by downstream systems. Returning `202 Accepted` decouples client latency from execution time and lets the worker process jobs independently.

## Why idempotency?

A client can lose the response after a successful submission and retry. Without an idempotency key, that uncertainty can create duplicate business transactions.

## Why dead letter instead of infinite retries?

Some failures are permanent. Bounded retries protect worker capacity and make failed work visible for an operational decision.

## Why SQLite?

For this repository, low setup cost matters. SQLite is enough to demonstrate durable state and local worker behavior. For distributed workers and higher throughput, move queue delivery to dedicated infrastructure and state to a production database.

## Why no LLM call yet?

The orchestration problem is deterministic. Adding an LLM without a real unstructured-data use case would add cost and variability without improving the design. AI belongs in a separate enrichment step with structured output, evaluation and human review where needed.
