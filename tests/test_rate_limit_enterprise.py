from __future__ import annotations

from collections import deque

import pytest

import core.rate_limit as rl


def _reset_rate_limit_memory() -> None:
    rl._BUCKETS.clear()
    rl._BANNED_IPS.clear()
    rl._LOCKED_KEYS.clear()
    rl._LOCK_HISTORY.clear()


@pytest.fixture(autouse=True)
def _clean_rate_limit_state():
    _reset_rate_limit_memory()
    yield
    _reset_rate_limit_memory()


def test_ban_ip_rejects_blank_ip():
    with pytest.raises(ValueError, match="ip must not be empty"):
        rl.ban_ip("", seconds=10)


def test_ban_ip_rejects_non_positive_seconds():
    with pytest.raises(ValueError, match="seconds must be positive"):
        rl.ban_ip("1.2.3.4", seconds=0)


def test_is_ip_banned_rejects_blank_ip():
    with pytest.raises(ValueError, match="ip must not be empty"):
        rl.is_ip_banned("")


def test_lock_key_and_remaining_seconds_memory(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(rl, "_now", lambda: now)

    rl.lock_key("resident:1", seconds=120)

    assert rl.is_key_locked("resident:1") is True
    assert rl.get_key_lock_seconds_remaining("resident:1") == 120

    now = 1060.0
    assert rl.get_key_lock_seconds_remaining("resident:1") == 60

    now = 1121.0
    assert rl.is_key_locked("resident:1") is False
    assert rl.get_key_lock_seconds_remaining("resident:1") == 0


def test_lock_key_rejects_blank_key():
    with pytest.raises(ValueError, match="key must not be empty"):
        rl.lock_key("", seconds=10)


def test_is_key_locked_rejects_blank_key():
    with pytest.raises(ValueError, match="key must not be empty"):
        rl.is_key_locked("")


def test_get_key_lock_seconds_remaining_rejects_blank_key():
    with pytest.raises(ValueError, match="key must not be empty"):
        rl.get_key_lock_seconds_remaining("")


def test_progressive_lock_seconds_memory_default_escalated_and_max(monkeypatch):
    now = 5000.0
    monkeypatch.setattr(rl, "_now", lambda: now)

    assert rl.get_progressive_lock_seconds("login:user1") == 600

    rl.lock_key("login:user1", seconds=10)
    assert rl.get_progressive_lock_seconds("login:user1") == 1800

    rl.lock_key("login:user1", seconds=10)
    assert rl.get_progressive_lock_seconds("login:user1") == 10800


def test_is_rate_limited_rejects_bad_inputs():
    with pytest.raises(ValueError, match="key must not be empty"):
        rl.is_rate_limited("", limit=1, window_seconds=60)

    with pytest.raises(ValueError, match="limit must be positive"):
        rl.is_rate_limited("k", limit=0, window_seconds=60)

    with pytest.raises(ValueError, match="window_seconds must be positive"):
        rl.is_rate_limited("k", limit=1, window_seconds=0)


def test_memory_rate_limit_snapshot_returns_sorted_rows(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(rl, "_now", lambda: now)

    rl._BUCKETS["alpha"] = deque([990.0, 995.0, 999.0])
    rl._BUCKETS["beta"] = deque([998.0])

    rows = rl.get_rate_limit_snapshot(window_seconds=20)

    assert [row["key"] for row in rows] == ["alpha", "beta"]
    assert rows[0]["hits"] == 3
    assert rows[0]["oldest_epoch"] == 990
    assert rows[0]["newest_epoch"] == 999
    assert rows[1]["hits"] == 1


def test_rate_limit_snapshot_prunes_empty_buckets(monkeypatch):
    now = 500.0
    monkeypatch.setattr(rl, "_now", lambda: now)

    rl._BUCKETS["stale"] = deque([100.0])
    rl._BUCKETS["fresh"] = deque([499.0])

    rows = rl.get_rate_limit_snapshot(window_seconds=10)

    assert [row["key"] for row in rows] == ["fresh"]
    assert "stale" not in rl._BUCKETS


def test_banned_and_locked_snapshots_memory(monkeypatch):
    now = 100.0
    monkeypatch.setattr(rl, "_now", lambda: now)

    rl._BANNED_IPS["1.1.1.1"] = 160.0
    rl._BANNED_IPS["2.2.2.2"] = 130.0
    rl._LOCKED_KEYS["user:a"] = 180.0
    rl._LOCKED_KEYS["user:b"] = 120.0

    banned_rows = rl.get_banned_ips_snapshot()
    locked_rows = rl.get_locked_keys_snapshot()

    assert [row["ip"] for row in banned_rows] == ["1.1.1.1", "2.2.2.2"]
    assert banned_rows[0]["seconds_remaining"] == 60
    assert banned_rows[1]["seconds_remaining"] == 30

    assert [row["key"] for row in locked_rows] == ["user:a", "user:b"]
    assert locked_rows[0]["seconds_remaining"] == 80
    assert locked_rows[1]["seconds_remaining"] == 20


def test_db_ban_ip_uses_state_store(monkeypatch):
    calls: list[tuple[str, str, float]] = []
    prune_calls: list[float] = []

    monkeypatch.setattr(rl, "_use_db_backend", lambda: True)
    monkeypatch.setattr(rl, "_now", lambda: 100.0)
    monkeypatch.setattr(rl, "upsert_state", lambda kind, key, until: calls.append((kind, key, until)))
    monkeypatch.setattr(rl, "_prune_db_if_needed", lambda now: prune_calls.append(now))

    rl.ban_ip("9.9.9.9", seconds=45)

    assert calls == [("banned_ip", "9.9.9.9", 145.0)]
    assert prune_calls == [100.0]


def test_db_is_ip_banned_uses_active_state_until(monkeypatch):
    monkeypatch.setattr(rl, "_use_db_backend", lambda: True)
    monkeypatch.setattr(rl, "_now", lambda: 200.0)
    monkeypatch.setattr(rl, "get_active_state_until", lambda kind, key: 250.0)

    assert rl.is_ip_banned("8.8.8.8") is True

    monkeypatch.setattr(rl, "get_active_state_until", lambda kind, key: 150.0)
    assert rl.is_ip_banned("8.8.8.8") is False


def test_db_lock_key_and_remaining(monkeypatch):
    state_calls: list[tuple[str, str, float]] = []
    history_calls: list[str] = []
    prune_calls: list[float] = []

    monkeypatch.setattr(rl, "_use_db_backend", lambda: True)
    monkeypatch.setattr(rl, "_now", lambda: 300.0)
    monkeypatch.setattr(
        rl,
        "upsert_state",
        lambda kind, key, until: state_calls.append((kind, key, until)),
    )
    monkeypatch.setattr(rl, "insert_lock_history", lambda key: history_calls.append(key))
    monkeypatch.setattr(rl, "_prune_db_if_needed", lambda now: prune_calls.append(now))

    rl.lock_key("staff:user", seconds=30)

    assert state_calls == [("locked_key", "staff:user", 330.0)]
    assert history_calls == ["staff:user"]
    assert prune_calls == [300.0]

    monkeypatch.setattr(rl, "get_active_state_until", lambda kind, key: 325.0)
    assert rl.is_key_locked("staff:user") is True
    assert rl.get_key_lock_seconds_remaining("staff:user") == 25

    monkeypatch.setattr(rl, "get_active_state_until", lambda kind, key: None)
    assert rl.get_key_lock_seconds_remaining("staff:user") == 0


def test_db_progressive_lock_seconds_branches(monkeypatch):
    monkeypatch.setattr(rl, "_use_db_backend", lambda: True)

    monkeypatch.setattr(rl, "recent_lock_count", lambda key, lookback: 0)
    assert rl.get_progressive_lock_seconds("user:x") == 600

    monkeypatch.setattr(rl, "recent_lock_count", lambda key, lookback: 1)
    assert rl.get_progressive_lock_seconds("user:x") == 1800

    monkeypatch.setattr(rl, "recent_lock_count", lambda key, lookback: 2)
    assert rl.get_progressive_lock_seconds("user:x") == 10800


def test_db_is_rate_limited_uses_store(monkeypatch):
    inserted: list[str] = []
    ensured: list[str] = []
    pruned: list[float] = []

    monkeypatch.setattr(rl, "_use_db_backend", lambda: True)
    monkeypatch.setattr(rl, "_now", lambda: 400.0)
    monkeypatch.setattr(rl, "_ensure_db_tables", lambda: ensured.append("ok"))
    monkeypatch.setattr(rl, "insert_rate_limit_event", lambda key: inserted.append(key))
    monkeypatch.setattr(rl, "count_rate_limit_events", lambda key, window: 3)
    monkeypatch.setattr(rl, "_prune_db_if_needed", lambda now: pruned.append(now))

    assert rl.is_rate_limited("api:test", limit=3, window_seconds=60) is False
    assert ensured == ["ok"]
    assert inserted == ["api:test"]
    assert pruned == [400.0]

    monkeypatch.setattr(rl, "count_rate_limit_events", lambda key, window: 4)
    assert rl.is_rate_limited("api:test", limit=3, window_seconds=60) is True


def test_db_snapshots_map_rows(monkeypatch):
    monkeypatch.setattr(rl, "_use_db_backend", lambda: True)
    monkeypatch.setattr(
        rl,
        "get_active_state_rows",
        lambda kind: (
            [{"key": "9.9.9.9", "seconds_remaining": 50, "until_epoch": 999}]
            if kind == "banned_ip"
            else [{"key": "user:a", "seconds_remaining": 30, "until_epoch": 888}]
        ),
    )
    monkeypatch.setattr(rl, "_ensure_db_tables", lambda: None)
    monkeypatch.setattr(rl, "_prune_db_if_needed", lambda now: None)
    monkeypatch.setattr(
        rl,
        "get_rate_limit_snapshot_rows",
        lambda window: [{"key": "rl:a", "hits": 7, "oldest_epoch": 1, "newest_epoch": 2}],
    )

    banned_rows = rl.get_banned_ips_snapshot()
    locked_rows = rl.get_locked_keys_snapshot()
    snapshot_rows = rl.get_rate_limit_snapshot(window_seconds=300)

    assert banned_rows == [
        {
            "ip": "9.9.9.9",
            "seconds_remaining": 50,
            "banned_until_epoch": 999,
        }
    ]
    assert locked_rows == [
        {
            "key": "user:a",
            "seconds_remaining": 30,
            "locked_until_epoch": 888,
        }
    ]
    assert snapshot_rows == [{"key": "rl:a", "hits": 7, "oldest_epoch": 1, "newest_epoch": 2}]
