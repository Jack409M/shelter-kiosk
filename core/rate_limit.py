from __future__ import annotations

import time
from collections import deque


_BUCKETS: dict[str, deque[float]] = {}
_BANNED_IPS: dict[str, float] = {}
_LOCKED_KEYS: dict[str, float] = {}
_LOCK_HISTORY: dict[str, deque[float]] = {}


def _prune_bucket(bucket: deque[float], window_seconds: int, now: float) -> None:
    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def _prune_expired_bans(now: float) -> None:
    expired = [ip for ip, until in _BANNED_IPS.items() if until <= now]
    for ip in expired:
        del _BANNED_IPS[ip]


def _prune_expired_locks(now: float) -> None:
    expired = [key for key, until in _LOCKED_KEYS.items() if until <= now]
    for key in expired:
        del _LOCKED_KEYS[key]


def _prune_lock_history(now: float, window_seconds: int = 86400) -> None:
    empty_keys: list[str] = []

    for key, history in _LOCK_HISTORY.items():
        _prune_bucket(history, window_seconds, now)
        if not history:
            empty_keys.append(key)

    for key in empty_keys:
        del _LOCK_HISTORY[key]


def _prune_stale_rate_limit_buckets(now: float, max_window_seconds: int = 86400) -> None:
    empty_keys: list[str] = []

    for key, bucket in _BUCKETS.items():
        _prune_bucket(bucket, max_window_seconds, now)
        if not bucket:
            empty_keys.append(key)

    for key in empty_keys:
        del _BUCKETS[key]


def ban_ip(ip: str, seconds: int) -> None:
    _BANNED_IPS[ip] = time.time() + seconds


def is_ip_banned(ip: str) -> bool:
    now = time.time()
    _prune_expired_bans(now)

    until = _BANNED_IPS.get(ip)
    if until is None:
        return False

    return until > now


def lock_key(key: str, seconds: int) -> None:
    now = time.time()
    _LOCKED_KEYS[key] = now + seconds

    history = _LOCK_HISTORY.get(key)
    if history is None:
        history = deque()
        _LOCK_HISTORY[key] = history

    history.append(now)
    _prune_bucket(history, 86400, now)


def is_key_locked(key: str) -> bool:
    now = time.time()
    _prune_expired_locks(now)

    until = _LOCKED_KEYS.get(key)
    if until is None:
        return False

    return until > now


def get_key_lock_seconds_remaining(key: str) -> int:
    now = time.time()
    _prune_expired_locks(now)

    until = _LOCKED_KEYS.get(key)
    if until is None:
        return 0

    return max(0, int(until - now))


def get_progressive_lock_seconds(key: str) -> int:
    now = time.time()
    _prune_lock_history(now)

    history = _LOCK_HISTORY.get(key)
    if history is None:
        return 600

    recent_lock_count_30m = 0
    cutoff_30m = now - 1800

    for ts in history:
        if ts >= cutoff_30m:
            recent_lock_count_30m += 1

    if recent_lock_count_30m >= 1:
        return 10800

    return 600


def is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    _prune_stale_rate_limit_buckets(now)

    bucket = _BUCKETS.get(key)

    if bucket is None:
        bucket = deque()
        _BUCKETS[key] = bucket

    _prune_bucket(bucket, window_seconds, now)

    if len(bucket) >= limit:
        return True

    bucket.append(now)
    return False


def get_banned_ips_snapshot() -> list[dict[str, int | str]]:
    now = time.time()
    _prune_expired_bans(now)

    rows: list[dict[str, int | str]] = []

    for ip, until in sorted(_BANNED_IPS.items(), key=lambda item: item[1], reverse=True):
        seconds_remaining = max(0, int(until - now))
        rows.append(
            {
                "ip": ip,
                "seconds_remaining": seconds_remaining,
                "banned_until_epoch": int(until),
            }
        )

    return rows


def get_rate_limit_snapshot(window_seconds: int = 3600) -> list[dict[str, int | str]]:
    now = time.time()
    rows: list[dict[str, int | str]] = []

    empty_keys: list[str] = []

    for key, bucket in _BUCKETS.items():
        _prune_bucket(bucket, window_seconds, now)

        if not bucket:
            empty_keys.append(key)
            continue

        rows.append(
            {
                "key": key,
                "hits": len(bucket),
                "oldest_epoch": int(bucket[0]),
                "newest_epoch": int(bucket[-1]),
            }
        )

    for key in empty_keys:
        del _BUCKETS[key]

    rows.sort(key=lambda row: int(row["hits"]), reverse=True)
    return rows


def get_locked_keys_snapshot() -> list[dict[str, int | str]]:
    now = time.time()
    _prune_expired_locks(now)

    rows: list[dict[str, int | str]] = []

    for key, until in sorted(_LOCKED_KEYS.items(), key=lambda item: item[1], reverse=True):
        seconds_remaining = max(0, int(until - now))
        rows.append(
            {
                "key": key,
                "seconds_remaining": seconds_remaining,
                "locked_until_epoch": int(until),
            }
        )

    return rows
