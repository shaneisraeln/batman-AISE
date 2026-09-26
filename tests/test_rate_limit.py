from batman.config import RateLimitConfig
from batman.gateway.rate_limit import SlidingWindowRateLimiter


def test_burst_limit_trips():
    rl = SlidingWindowRateLimiter(RateLimitConfig(requests_per_minute=1000, burst=3))
    now = 100.0
    assert rl.check("k", now=now).allowed
    assert rl.check("k", now=now).allowed
    assert rl.check("k", now=now).allowed
    blocked = rl.check("k", now=now)
    assert not blocked.allowed
    assert blocked.reason == "burst_exceeded"


def test_sustained_rate_limit():
    rl = SlidingWindowRateLimiter(RateLimitConfig(requests_per_minute=5, burst=100))
    # Spread requests across the window so burst never trips.
    for i in range(5):
        assert rl.check("k", now=100.0 + i * 5).allowed
    res = rl.check("k", now=125.0)
    assert not res.allowed
    assert res.reason == "rate_exceeded"


def test_separate_keys_independent():
    rl = SlidingWindowRateLimiter(RateLimitConfig(requests_per_minute=1000, burst=1))
    assert rl.check("a", now=1.0).allowed
    assert rl.check("b", now=1.0).allowed  # different key, fresh budget
