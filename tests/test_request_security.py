from __future__ import annotations


def test_ip_not_banned_by_default():
    from core.rate_limit import is_ip_banned

    assert is_ip_banned("127.0.0.1") is False


def test_rate_limit_allows_first_request():
    from core.rate_limit import is_rate_limited

    key = "test-key-allow"
    assert is_rate_limited(key, limit=5, window_seconds=60) is False


def test_rate_limit_blocks_after_limit():
    from core.rate_limit import is_rate_limited

    key = "test-key-block"

    # hit the limit
    for _ in range(5):
        is_rate_limited(key, limit=5, window_seconds=60)

    # next one should be blocked
    assert is_rate_limited(key, limit=5, window_seconds=60) is True
