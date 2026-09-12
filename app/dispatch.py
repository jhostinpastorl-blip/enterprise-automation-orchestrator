from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import redis


class DispatchQueue(ABC):
    brokered: bool = False

    @abstractmethod
    def publish(self, request_id: str) -> None:
        """Publish a persisted request for worker execution."""

    @abstractmethod
    def consume(self, timeout_seconds: int = 1) -> str | None:
        """Return the next request ID, or None when no brokered item is available."""


class DatabaseDispatchQueue(DispatchQueue):
    """No external broker: workers claim eligible rows directly from durable state."""

    brokered = False

    def publish(self, request_id: str) -> None:
        return None

    def consume(self, timeout_seconds: int = 1) -> str | None:
        return None


class RedisDispatchQueue(DispatchQueue):
    """Use a Redis list as a lightweight broker while keeping the database authoritative."""

    brokered = True

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        queue_name: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.queue_name = queue_name or os.getenv("REDIS_QUEUE_NAME", "automation:requests")
        self.client = client

    def _client(self):
        if self.client is None:
            self.client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self.client

    def publish(self, request_id: str) -> None:
        self._client().rpush(self.queue_name, request_id)

    def consume(self, timeout_seconds: int = 1) -> str | None:
        item = self._client().blpop(self.queue_name, timeout=timeout_seconds)
        if item is None:
            return None
        _, request_id = item
        if isinstance(request_id, bytes):
            return request_id.decode()
        return str(request_id)


def get_dispatch_queue() -> DispatchQueue:
    backend = os.getenv("DISPATCH_BACKEND", "database").strip().lower()
    if backend == "database":
        return DatabaseDispatchQueue()
    if backend == "redis":
        return RedisDispatchQueue()
    raise ValueError(f"Unsupported DISPATCH_BACKEND: {backend}")
