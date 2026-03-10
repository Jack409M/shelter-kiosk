from __future__ import annotations

import time
from collections import deque


_BUCKETS: dict[str, deque[float]] = {}
_BANNED_IPS: dict[str, float] = {}


def _prune_bucket(bucket: deque[float], window_seconds: int, now: float) -> None:
    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def _prune_expired_bans(now: float) -> None:
    expired = [ip for ip, until in _BANNED_IPS.items() if until <= now]
    for ip in expired:
        del _BANNED_IPS[ip]


def ban_ip(ip: str, seconds: int) -> None:
    _BANNED_IPS[ip] = time.time() + seconds


def is_ip_banned(ip: str) -> bool:
    now = time.time()
    _prune_expired_bans(now)

    until = _BANNED_IPS.get(ip)
    if until is None:
        return False

    return until > now


def is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
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
