"""Guessing and flooding, slowed to pointlessness (specs/008-api-auth-audit/research.md §8).

In memory, on the monotonic clock. A Pi without a battery-backed clock can boot
hours in the past and be corrected by the network a minute later; a lockout on
wall time would then last hours, or end at once. The monotonic clock does not
jump. A restart forgets everything, which nobody on the network can cause.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    tokens: float
    at: float


@dataclass
class Throttle:
    failed_attempts: int = 10
    failed_window: float = 300.0
    lockout: float = 900.0
    burst: int = 10
    per_second: float = 1.0
    monotonic: Callable[[], float] = time.monotonic
    _failures: dict[str, deque[float]] = field(default_factory=dict)
    _locked_until: dict[str, float] = field(default_factory=dict)
    _buckets: dict[str, _Bucket] = field(default_factory=dict)

    # --- failed authentication, per source address ------------------------------

    def fail(self, source: str) -> None:
        now = self.monotonic()
        window = self._failures.setdefault(source, deque())
        window.append(now)
        while window and window[0] <= now - self.failed_window:
            window.popleft()
        if len(window) >= self.failed_attempts:
            self._locked_until[source] = now + self.lockout
            window.clear()

    def locked(self, source: str) -> float | None:
        """Seconds until the source may try again, or None."""
        until = self._locked_until.get(source)
        if until is None:
            return None
        left = until - self.monotonic()
        if left <= 0:
            del self._locked_until[source]
            return None
        return left

    # --- commands, per credential ---------------------------------------------------

    def take(self, credential_id: str) -> float | None:
        """Spend one command. None if allowed, else seconds until the next is."""
        now = self.monotonic()
        bucket = self._buckets.get(credential_id)
        if bucket is None:
            bucket = self._buckets[credential_id] = _Bucket(float(self.burst), now)
        bucket.tokens = min(float(self.burst), bucket.tokens + (now - bucket.at) * self.per_second)
        bucket.at = now
        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return None
        return (1 - bucket.tokens) / self.per_second

    def reset(self) -> None:
        self._failures.clear()
        self._locked_until.clear()
        self._buckets.clear()
