# Performance validation protocol

## Goal

Measure the reference system with explicit numbers instead of describing it as scalable without evidence.

The first harness measures **API admission performance**: validation, persistence and dispatch of automation requests. It does not claim end-to-end RPA or downstream-system throughput.

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

Do not invent an SLO before measuring the system. After several reproducible runs, define a reference objective that is explicitly scoped, for example:

> Under the documented local distributed test environment and workload, 99% of automation submissions should be accepted within the measured threshold while maintaining zero persistence errors.

The threshold must come from measured evidence, not from a desired CV statement.

## Portfolio evidence

The useful evidence is not a large benchmark number. The useful evidence is the engineering process:

1. define the boundary being measured;
2. make the workload reproducible;
3. capture percentile latency rather than averages alone;
4. identify saturation and failure behavior;
5. document environmental limitations;
6. use results to decide what should be optimized next.
