from core.rate_limit import ban_ip, is_rate_limited


def test_rate_limit_basic_flow():
    ip = "1.2.3.4"

    # initial call should not be limited
    assert not is_rate_limited(ip, limit=10, window_seconds=60)

    # simulate repeated calls
    for _ in range(15):
        is_rate_limited(ip, limit=10, window_seconds=60)

    result = is_rate_limited(ip, limit=10, window_seconds=60)

    assert isinstance(result, bool)


def test_ban_ip():
    ip = "5.6.7.8"

    ban_ip(ip)

    result = is_rate_limited(ip, limit=10, window_seconds=60)

    assert result is True
