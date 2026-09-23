"""
Shared process-local rolling-window rate limiter.

Extracted from backend/routers/research.py's ResearchStartRateLimiter so
other routers (e.g. the general chat endpoint) can reuse the same pattern
instead of re-implementing it. research.py keeps importing this under its
original name for backward compatibility with existing tests that patch
`research.ResearchStartRateLimiter`.
"""

import asyncio
import time
from collections import defaultdict, deque


class RollingWindowRateLimiter:
    """Small process-local rolling-window limiter, keyed per user_id.

    It intentionally does not attempt distributed enforcement: timestamps are
    lost after restart and are not shared across worker processes.
    """

    def __init__(self, limit: int = 10, window_seconds: float = 3600) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._starts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, user_id: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            starts = self._starts[user_id]
            while starts and now - starts[0] >= self.window_seconds:
                starts.popleft()
            if len(starts) >= self.limit:
                return False
            starts.append(now)
            return True

    def reset(self) -> None:
        """Clear process-local state; used only by isolated tests."""
        self._starts.clear()
