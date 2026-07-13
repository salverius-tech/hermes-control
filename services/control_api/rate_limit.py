from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        if max_requests < 1 or window_seconds <= 0:
            raise ValueError("rate limiter settings must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        with self._lock:
            requests = self._requests.setdefault(key, deque())
            cutoff = current - self.window_seconds
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= self.max_requests:
                return False
            requests.append(current)
            return True
