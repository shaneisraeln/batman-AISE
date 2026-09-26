"""Sliding-window rate limiter with a burst allowance.

Limits are enforced per dimension (API key and/or session). State is bounded
and in-memory, which is appropriate for the MVP prototype.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from batman.config import RateLimitConfig


class RateLimitResult:
    def __init__(self, allowed: bool, retry_after: float = 0.0, reason: str = ""):
        self.allowed = allowed
        self.retry_after = retry_after
        self.reason = reason


class SlidingWindowRateLimiter:
    """Rolling 60-second window per key, plus a short burst window.

    - ``requests_per_minute`` caps sustained rate over the rolling minute.
    - ``burst`` caps requests within a 1-second window.
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self._windows: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _clean(self, dq: deque[float], now: float, horizon: float) -> None:
        while dq and dq[0] <= now - horizon:
            dq.popleft()

    def check(self, key: str, now: float | None = None) -> RateLimitResult:
        now = now if now is not None else time.monotonic()
        with self._lock:
            dq = self._windows.setdefault(key, deque())
            self._clean(dq, now, 60.0)

            # Burst check: requests in the last 1s.
            burst_count = sum(1 for t in dq if t > now - 1.0)
            if burst_count >= self.config.burst:
                return RateLimitResult(False, retry_after=1.0, reason="burst_exceeded")

            # Sustained check: requests in the last 60s.
            if len(dq) >= self.config.requests_per_minute:
                oldest = dq[0]
                retry = max(0.0, 60.0 - (now - oldest))
                return RateLimitResult(False, retry_after=retry, reason="rate_exceeded")

            dq.append(now)
            return RateLimitResult(True)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._windows.clear()
            else:
                self._windows.pop(key, None)
