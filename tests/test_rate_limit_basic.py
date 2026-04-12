from __future__ import annotations

import time

from core.rate_limit import ban_ip, is_ip_banned, is_rate_limited


def test_rate_limit_triggers_exactly_at_limit():
    key = "rl:test:exact"

    limit = 5
    window = 60

    # first N should pass
    for i in range(limit):
        assert is_rate_limited(key, limit=limit, window_seconds=window) is False

    # next one should trip
    assert is_rate_limited(key, limit=limit, window_seconds=window) is True


def test_rate_limit_resets_after_window():
    key = "rl:test:reset"

    limit = 3
    window = 1  # short window for test

    for _ in range(limit + 1):
        is_rate_limited(key, limit=limit, window_seconds=window)

    # should be limited now
    assert is_rate_limited(key, limit=limit, window_seconds=window) is True

    # wait for window to expire
    time.sleep(1.2)

    # should reset
    assert is_rate_limited(key, limit=limit, window_seconds=window) is False


def test_rate_limit_is_isolated_per_key():
    key_a = "rl:test:a"
    key_b = "rl:test:b"

    limit = 2

    # trip key A
    is_rate_limited(key_a, limit=limit, window_seconds=60)
    is_rate_limited(key_a, limit=limit, window_seconds=60)
    assert is_rate_limited(key_a, limit=limit, window_seconds=60) is True

    # key B should not be affected
    assert is_rate_limited(key_b, limit=limit, window_seconds=60) is False


def test_ban_ip_and_expiration():
    ip = "9.9.9.9"

    ban_ip(ip, seconds=1)

    assert is_ip_banned(ip) is True

    time.sleep(1.2)

    assert is_ip_banned(ip) is False


def test_multiple_bans_do_not_conflict():
    ip1 = "10.0.0.1"
    ip2 = "10.0.0.2"

    ban_ip(ip1, seconds=2)
    ban_ip(ip2, seconds=1)

    assert is_ip_banned(ip1) is True
    assert is_ip_banned(ip2) is True

    time.sleep(1.2)

    # ip2 should expire first
    assert is_ip_banned(ip1) is True
    assert is_ip_banned(ip2) is False


def test_rate_limit_does_not_ban_automatically():
    key = "rl:test:no-ban"

    for _ in range(20):
        is_rate_limited(key, limit=5, window_seconds=60)

    # ensure rate limit does NOT implicitly ban
    assert is_ip_banned("1.2.3.4") is False
