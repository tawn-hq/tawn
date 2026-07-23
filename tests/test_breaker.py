from tawn.model.breaker import CircuitBreaker


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_starts_closed_and_allows():
    b = CircuitBreaker()
    assert b.state == "closed"
    assert b.allow() is True


def test_opens_after_threshold_failures():
    b = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        b.record_failure()
    assert b.state == "open"
    assert b.allow() is False


def test_success_resets_failure_count():
    b = CircuitBreaker(failure_threshold=3)
    b.record_failure()
    b.record_failure()
    b.record_success()
    b.record_failure()
    b.record_failure()
    assert b.state == "closed"  # never hit 3 consecutive


def test_half_open_after_cooldown_allows_one_probe():
    clock = Clock()
    b = CircuitBreaker(failure_threshold=1, cooldown_s=60.0, clock=clock)
    b.record_failure()
    assert b.allow() is False
    clock.t = 61.0
    assert b.state == "half_open"
    assert b.allow() is True  # the single probe
    assert b.allow() is False  # no second call while probing


def test_probe_success_closes_probe_failure_reopens():
    clock = Clock()
    b = CircuitBreaker(failure_threshold=1, cooldown_s=60.0, clock=clock)
    b.record_failure()
    clock.t = 61.0
    assert b.allow() is True
    b.record_success()
    assert b.state == "closed"

    b.record_failure()  # open again
    clock.t = 122.0
    assert b.allow() is True
    b.record_failure()  # probe fails
    assert b.state == "open"
    assert b.allow() is False
