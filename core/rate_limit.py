from __future__ import annotations

import time
from collections import deque

_BUCKETS: dict[str, deque[float]] = {}
_BANNED_IPS: dict[str, float] = {}


def ban_ip(ip: str, seconds: int) -> None:
    _BANNED_IPS[ip] = time.time() + seconds


def is_ip_banned(ip: str) -> bool:
    until = _BANNED_IPS.get(ip)

    if until is None:
        return False

    if until <= time.time():
        del _BANNED_IPS[ip]
        return False

    return True


def is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    bucket = _BUCKETS.get(key)

    if bucket is None:
        bucket = deque()
        _BUCKETS[key] = bucket

    cutoff = now - window_seconds

    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if len(bucket) >= limit:
        return True

    bucket.append(now)
    return False
