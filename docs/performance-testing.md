# Performance validation protocol

## Goal

Measure the reference system with explicit numbers instead of describing it as scalable without evidence.

The first harness measures **API admission performance**: validation, persistence and dispatch of automation requests. It does not claim end-to-end RPA or downstream-system throughput.

## Measured CI reference baseline

A repeatable GitHub Actions benchmark now runs on every push to `main`.

Reference run characteristics:

- environment: GitHub Actions hosted runner, Ubuntu 24.04;
- persistence: SQLite reference benchmark database;
- dispatch mode: database;
- requests: 500;
- concurrency: 25;
- accepted: 500;
- failed: 0;
- elapsed: 7.552 seconds;
- throughput: 66.21 requests/second;
- mean admission latency: 374.36 ms;
- p50: 345.65 ms;
- p95: 730.08 ms;
- p99: 1619.25 ms;
- maximum: 1937.26 ms.

These figures are a **single synthetic CI admission baseline**, not a production benchmark. They do not measure PostgreSQL + Redis distributed capacity, worker throughput, UiPath execution, SAP latency or business-process completion time. Hosted-runner performance may also vary between CI executions.

## Provisional engineering target

Until multiple comparable runs exist, this repository does not claim a formal SLO. For the exact CI workload above, the current engineering target is:

- zero admission failures;
- p95 admission latency below 1 second;
- no persistence errors.

This is a portfolio/reference target scoped to the synthetic admission test. It must not be represented as a customer-facing or production SLO.

## Local distributed topology

Start the production-like local topology:

```bash
docker compose -f compose.production.yaml up --build
```

Then run:

```bash
python scripts/load_test.py \
  --base-url http://localhost:8000 \
  --requests 1000 \
  --concurrency 50
```

If API-key protection is enabled:

```bash
python scripts/load_test.py \
  --base-url http://localhost:8000 \
  --requests 1000 \
  --concurrency 50 \
  --api-key YOUR_TEST_KEY
```

## Record these results

For each run record:

- environment and machine/container resources;
- PostgreSQL and Redis topology;
- request count;
- concurrency;
- accepted versus failed requests;
- total duration;
- requests/second;
- mean latency;
- p50 latency;
- p95 latency;
- p99 latency;
- maximum latency;
- failure breakdown.

Do not compare results from different machines or cloud plans as if they were equivalent.

## Suggested test matrix

| Run | Requests | Concurrency | Purpose |
| --- | ---: | ---: | --- |
| Baseline | 200 | 10 | Validate harness and stable behavior |
| Moderate | 1,000 | 25 | Observe normal concurrency |
| Higher | 2,000 | 50 | Find latency growth and saturation signs |
| Stress | 5,000 | 100 | Discover the failure/saturation boundary |

The exact numbers are synthetic portfolio tests, not enterprise production benchmarks.

## What this does not prove

Admission throughput does not equal business-process throughput. Real automation capacity also depends on:

- worker count;
- target API quotas;
- robot licenses and available runtimes;
- SAP or desktop UI latency;
- transaction duration;
- downstream failure rates;
- retry volume;
- database and broker sizing.

A future end-to-end benchmark should use a deterministic synthetic adapter so worker processing can be measured without making claims about real UiPath, SAP or third-party systems.

## SLO discussion

A formal SLO should be based on repeated comparable measurements, a clearly defined service boundary and a relevant consumer expectation. One CI run is insufficient evidence.

A future distributed benchmark should separately define objectives for:

1. API admission latency and failure rate;
2. queue wait time;
3. worker processing latency using a deterministic adapter;
4. recovery behavior under downstream throttling;
5. dead-letter and replay behavior.

## Portfolio evidence

The useful evidence is not a large benchmark number. The useful evidence is the engineering process:

1. define the boundary being measured;
2. make the workload reproducible;
3. capture percentile latency rather than averages alone;
4. identify saturation and failure behavior;
5. document environmental limitations;
6. use results to decide what should be optimized next.
