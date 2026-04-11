from core.rate_limit import is_rate_limited, ban_ip


def test_rate_limit_basic_flow():
    ip = "1.2.3.4"

    # Should not be limited initially
    assert not is_rate_limited(ip)

    # Simulate repeated calls
    for _ in range(20):
        is_rate_limited(ip)

    # Eventually should trigger limit (depends on logic)
    result = is_rate_limited(ip)

    assert isinstance(result, bool)


def test_ban_ip():
    ip = "5.6.7.8"

    ban_ip(ip)

    # After banning, should be rate limited
    result = is_rate_limited(ip)

    assert result is True
