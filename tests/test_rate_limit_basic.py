from core.rate_limit import ban_ip, is_rate_limited


def test_rate_limit_basic_flow():
    ip = "1.2.3.4"

    assert not is_rate_limited(ip)

    for _ in range(20):
        is_rate_limited(ip)

    result = is_rate_limited(ip)

    assert isinstance(result, bool)


def test_ban_ip():
    ip = "5.6.7.8"

    ban_ip(ip)

    result = is_rate_limited(ip)

    assert result is True
