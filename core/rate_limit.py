from __future__ import annotations

import time
from collections import deque

_BUCKETS: dict[str, deque[float]] = {}


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
