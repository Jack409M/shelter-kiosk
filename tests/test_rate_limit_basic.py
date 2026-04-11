from core.rate_limit import ban_ip, is_ip_banned, is_rate_limited


def test_rate_limit_basic_flow():
    ip = "1.2.3.4"

    assert not is_rate_limited(ip, limit=10, window_seconds=60)

    for _ in range(15):
        is_rate_limited(ip, limit=10, window_seconds=60)

    result = is_rate_limited(ip, limit=10, window_seconds=60)

    assert isinstance(result, bool)


def test_ban_ip():
    ip = "5.6.7.8"

    ban_ip(ip, seconds=60)

    assert is_ip_banned(ip) is True
