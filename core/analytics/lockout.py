"""Admin login brute-force protection: ADMIN_LOGIN_MAX_FAILS failures per IP + username lock
that pair for ADMIN_LOGIN_LOCK_MINUTES. In memory (the server runs as one process)."""

import time
from collections.abc import Callable

from games.constants import ADMIN_LOGIN_LOCK_MINUTES, ADMIN_LOGIN_MAX_FAILS

PRUNE_ABOVE_KEYS = 10_000


class LoginLockout:
    def __init__(
        self,
        max_fails: int = ADMIN_LOGIN_MAX_FAILS,
        lock_seconds: float = ADMIN_LOGIN_LOCK_MINUTES * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_fails = max_fails
        self.lock_seconds = lock_seconds
        self.clock = clock
        self._fails: dict[tuple[str, str], list[float]] = {}

    @staticmethod
    def key(ip: str, username: str) -> tuple[str, str]:
        return ip, username.strip().lower()

    def _recent(self, key: tuple[str, str]) -> list[float]:
        now = self.clock()
        recent = [t for t in self._fails.get(key, []) if now - t < self.lock_seconds]
        if recent:
            self._fails[key] = recent
        else:
            self._fails.pop(key, None)
        return recent

    def locked(self, key: tuple[str, str]) -> bool:
        return len(self._recent(key)) >= self.max_fails

    def failed(self, key: tuple[str, str]) -> None:
        if len(self._fails) > PRUNE_ABOVE_KEYS:
            for stale in [k for k in self._fails if not self._recent(k)]:
                self._fails.pop(stale, None)
        self._fails.setdefault(key, []).append(self.clock())

    def succeeded(self, key: tuple[str, str]) -> None:
        self._fails.pop(key, None)

    def reset(self) -> None:
        self._fails.clear()


admin_lockout = LoginLockout()
