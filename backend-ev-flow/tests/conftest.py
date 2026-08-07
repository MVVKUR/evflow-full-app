import os
import pytest

requires_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set; skipping DB-backed tests",
)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """No test starts with another test's rate-limit budget already spent.

    api.rate_limit holds its counters in module-global tables that live for the
    whole process, so without this a test that logs in a few times leaves the
    next one closer to a 429 -- and the failure lands in whichever test happens to
    run last, not in the one that spent the budget. Runs on every test rather
    than only the rate-limit ones, because the endpoints that are now budgeted
    (login, register, forgot-password, wallet top-up, session start) are touched
    all over this suite.
    """
    from api import rate_limit
    rate_limit.reset()
    yield
    rate_limit.reset()


class FakeClock:
    """Stands in for the `time` module inside api.rate_limit.

    Window expiry is the one limiter behaviour that cannot be observed without
    the passage of time, and the windows in production are 5 minutes to an hour.
    Nothing in this suite sleeps; the clock is moved by hand instead.
    """

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def rate_limit_clock(monkeypatch) -> FakeClock:
    from api import rate_limit
    fake = FakeClock()
    monkeypatch.setattr(rate_limit, "time", fake)
    return fake
