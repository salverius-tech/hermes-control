import pytest

from services.control_api.rate_limit import RateLimiter


@pytest.mark.unit
def test_rate_limiter_rejects_requests_after_limit_and_expires_them():
    limiter = RateLimiter(max_requests=2, window_seconds=10)

    assert limiter.allow("client", now=100)
    assert limiter.allow("client", now=101)
    assert not limiter.allow("client", now=102)
    assert limiter.allow("client", now=111)


@pytest.mark.unit
def test_rate_limiter_tracks_clients_independently():
    limiter = RateLimiter(max_requests=1)

    assert limiter.allow("first", now=100)
    assert limiter.allow("second", now=100)
    assert not limiter.allow("first", now=101)


@pytest.mark.unit
def test_rate_limiter_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        RateLimiter(0)
    with pytest.raises(ValueError):
        RateLimiter(1, window_seconds=0)
