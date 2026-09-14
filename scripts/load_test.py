from __future__ import annotations

import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import httpx


@dataclass
class Sample:
    latency_ms: float
    status_code: int | None
    error: str | None = None


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))
    return ordered[index]


def submit_one(base_url: str, api_key: str | None, sequence: int, timeout: float) -> Sample:
    headers = {"X-API-Key": api_key} if api_key else {}
    payload = {
        "process": "synthetic_load",
        "target": "benchmark-target",
        "execution_channel": "api",
        "payload": {"sequence": sequence},
        "idempotency_key": f"load-test-{time.time_ns()}-{sequence}",
        "max_attempts": 1,
    }
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/automation-requests",
                headers=headers,
                json=payload,
            )
        latency_ms = (time.perf_counter() - started) * 1000
        return Sample(latency_ms=latency_ms, status_code=response.status_code)
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return Sample(latency_ms=latency_ms, status_code=None, error=str(exc))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Synthetic load harness for API admission latency. "
            "It measures request acceptance only, not end-to-end automation completion."
        )
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    started = time.perf_counter()
    samples: list[Sample] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                submit_one,
                args.base_url,
                args.api_key,
                sequence,
                args.timeout,
            )
            for sequence in range(args.requests)
        ]
        for future in as_completed(futures):
            samples.append(future.result())

    elapsed = time.perf_counter() - started
    latencies = [sample.latency_ms for sample in samples]
    accepted = sum(1 for sample in samples if sample.status_code == 202)
    failures = [sample for sample in samples if sample.status_code != 202]

    print("Enterprise Automation Orchestrator - admission load result")
    print(f"requests={len(samples)} concurrency={args.concurrency}")
    print(f"accepted={accepted} failed={len(failures)}")
    print(f"elapsed_seconds={elapsed:.3f}")
    print(f"throughput_requests_per_second={len(samples) / elapsed:.2f}")
    print(f"latency_mean_ms={statistics.fmean(latencies):.2f}")
    print(f"latency_p50_ms={percentile(latencies, 0.50):.2f}")
    print(f"latency_p95_ms={percentile(latencies, 0.95):.2f}")
    print(f"latency_p99_ms={percentile(latencies, 0.99):.2f}")
    print(f"latency_max_ms={max(latencies):.2f}")

    if failures:
        by_status: dict[str, int] = {}
        for sample in failures:
            key = str(sample.status_code) if sample.status_code is not None else "error"
            by_status[key] = by_status.get(key, 0) + 1
        print(f"failure_breakdown={by_status}")
        first_errors = [sample.error for sample in failures if sample.error][:3]
        if first_errors:
            print(f"sample_errors={first_errors}")


if __name__ == "__main__":
    main()
