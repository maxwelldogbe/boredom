"""Per-IP limits on register and login (in memory; the server runs as one process)."""

import time
from collections.abc import Callable

from games.constants import AUTH_RATE_LIMIT_PER_MIN
from rooms.validation import RateLimiter

PRUNE_ABOVE_KEYS = 10_000


class KeyedRateLimiter:
    """One sliding window (one minute by default) per key."""

    def __init__(
        self,
        limit: int = AUTH_RATE_LIMIT_PER_MIN,
        clock: Callable[[], float] = time.monotonic,
        window: float = 60.0,
    ) -> None:
        self.limit = limit
        self.clock = clock
        self.window = window
        self._limiters: dict[str, RateLimiter] = {}

    def allow(self, key: str) -> bool:
        """Record and allow a call for `key`, or return False if its window is full."""
        if len(self._limiters) > PRUNE_ABOVE_KEYS:
            self._limiters = {k: v for k, v in self._limiters.items() if not v.idle()}
        limiter = self._limiters.get(key)
        if limiter is None:
            limiter = RateLimiter(self.limit, self.clock, window=self.window)
            self._limiters[key] = limiter
        return limiter.allow()

    def reset(self) -> None:
        self._limiters.clear()


register_limiter = KeyedRateLimiter()
login_limiter = KeyedRateLimiter()
