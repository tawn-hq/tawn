"""Per-provider circuit breaker (spec §15.3).

closed → open after N consecutive failures; open → half_open after the
cooldown; half_open admits exactly one probe — success closes, failure
reopens. Keeps a dead provider from eating every request's timeout.
"""

import time
from collections.abc import Callable


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._probing = False

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self.cooldown_s:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        s = self.state
        if s == "closed":
            return True
        if s == "half_open" and not self._probing:
            self._probing = True
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._probing = False

    def record_failure(self) -> None:
        if self._probing or self.state == "half_open":
            # failed probe → back to open, restart the cooldown
            self._opened_at = self._clock()
            self._probing = False
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = self._clock()
            self._failures = 0
