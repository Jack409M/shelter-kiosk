from __future__ import annotations

import time
from collections import deque
from threading import RLock
from typing import Final

from flask import has_app_context, g

from core.rate_limit_store import count_rate_limit_events
from core.rate_limit_store import ensure_tables as ensure_rate_limit_store_tables
from core.rate_limit_store import get_rate_limit_snapshot_rows
from core.rate_limit_store import insert_lock_history
from core.rate_limit_store import insert_rate_limit_event
from core.rate_limit_store import prune_if_needed as prune_rate_limit_store_if_needed
from core.rate_limit_store import recent_lock_count
from core.security_state_store import get_active_state_rows
from core.security_state_store import get_active_state_until
from core.security_state_store import upsert_state


_DEFAULT_PROGRESSIVE_LOCK_SECONDS: Final[int] = 600
_ESCALATED_PROGRESSIVE_LOCK_SECONDS: Final[int] = 1800
_MAX_PROGRESSIVE_LOCK_SECONDS: Final[int] = 10800
_PROGRESSIVE_LOCK_LOOKBACK_SECONDS: Final[int] = 1800
_MEMORY_HISTORY_RETENTION_SECONDS: Final[int] = 86400
_MEMORY_BUCKET_RETENTION_SECONDS: Final[int] = 86400

_BUCKETS: dict[str, deque[float]] = {}
_BANNED_IPS: dict[str, float] = {}
_LOCKED_KEYS: dict[str, float] = {}
_LOCK_HISTORY: dict[str, deque[float]] = {}
_STATE_LOCK = RLock()


def _now() -> float:
    return time.time()


def _require_text(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    return text


def _require_positive_int(value: object, *, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as err:
        raise ValueError(f"{label} must be an integer") from err

    if number <= 0:
        raise ValueError(f"{label} must be positive")

    return number


def _prune_bucket(bucket: deque[float], window_seconds: int, now: float) -> None:
    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def _prune_expired_state(state: dict[str, float], now: float) -> None:
    expired_keys = [key for key, until in state.items() if until <= now]
    for key in expired_keys:
        del state[key]


def _prune_lock_history(
    now: float,
    window_seconds: int = _MEMORY_HISTORY_RETENTION_SECONDS,
) -> None:
    empty_keys: list[str] = []

    for key, history in _LOCK_HISTORY.items():
        _prune_bucket(history, window_seconds, now)
        if not history:
            empty_keys.append(key)

    for key in empty_keys:
        del _LOCK_HISTORY[key]


def _prune_stale_rate_limit_buckets(
    now: float,
    max_window_seconds: int = _MEMORY_BUCKET_RETENTION_SECONDS,
) -> None:
    empty_keys: list[str] = []

    for key, bucket in _BUCKETS.items():
        _prune_bucket(bucket, max_window_seconds, now)
        if not bucket:
            empty_keys.append(key)

    for key in empty_keys:
        del _BUCKETS[key]


def _db_kind() -> str:
    if not has_app_context():
        return ""
    kind_value = g.get("db_kind")
    return str(kind_value or "").strip().lower()


def _use_db_backend() -> bool:
    return _db_kind() in {"pg", "sqlite"}


def _ensure_db_tables() -> None:
    if not has_app_context():
        return

    ensure_rate_limit_store_tables()


def _prune_db_if_needed(now: float) -> None:
    if not has_app_context():
        return

    prune_rate_limit_store_if_needed(now)


def _memory_ban_ip(ip: str, seconds: int) -> None:
    with _STATE_LOCK:
        _BANNED_IPS[ip] = _now() + seconds


def _memory_is_ip_banned(ip: str) -> bool:
    with _STATE_LOCK:
        now = _now()
        _prune_expired_state(_BANNED_IPS, now)

        until = _BANNED_IPS.get(ip)
        if until is None:
            return False

        return until > now


def _memory_lock_key(key: str, seconds: int) -> None:
    with _STATE_LOCK:
        now = _now()
        _LOCKED_KEYS[key] = now + seconds

        history = _LOCK_HISTORY.get(key)
        if history is None:
            history = deque()
            _LOCK_HISTORY[key] = history

        history.append(now)
        _prune_bucket(history, _MEMORY_HISTORY_RETENTION_SECONDS, now)


def _memory_is_key_locked(key: str) -> bool:
    with _STATE_LOCK:
        now = _now()
        _prune_expired_state(_LOCKED_KEYS, now)

        until = _LOCKED_KEYS.get(key)
        if until is None:
            return False

        return until > now


def _memory_get_key_lock_seconds_remaining(key: str) -> int:
    with _STATE_LOCK:
        now = _now()
        _prune_expired_state(_LOCKED_KEYS, now)

        until = _LOCKED_KEYS.get(key)
        if until is None:
            return 0

        return max(0, int(until - now))


def _memory_get_progressive_lock_seconds(key: str) -> int:
    with _STATE_LOCK:
        now = _now()
        _prune_lock_history(now)

        history = _LOCK_HISTORY.get(key)
        if history is None:
            return _DEFAULT_PROGRESSIVE_LOCK_SECONDS

        cutoff = now - _PROGRESSIVE_LOCK_LOOKBACK_SECONDS
        recent_count = sum(1 for timestamp in history if timestamp >= cutoff)

        if recent_count >= 2:
            return _MAX_PROGRESSIVE_LOCK_SECONDS

        if recent_count >= 1:
            return _ESCALATED_PROGRESSIVE_LOCK_SECONDS

        return _DEFAULT_PROGRESSIVE_LOCK_SECONDS


def _memory_is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    with _STATE_LOCK:
        now = _now()
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


def ban_ip(ip: str, seconds: int) -> None:
    ip_clean = _require_text(ip, label="ip")
    seconds_clean = _require_positive_int(seconds, label="seconds")

    if _use_db_backend():
        now = _now()
        upsert_state("banned_ip", ip_clean, now + seconds_clean)
        _prune_db_if_needed(now)
        return

    _memory_ban_ip(ip_clean, seconds_clean)


def is_ip_banned(ip: str) -> bool:
    ip_clean = _require_text(ip, label="ip")

    if _use_db_backend():
        until = get_active_state_until("banned_ip", ip_clean)
        return until is not None and until > _now()

    return _memory_is_ip_banned(ip_clean)


def lock_key(key: str, seconds: int) -> None:
    key_clean = _require_text(key, label="key")
    seconds_clean = _require_positive_int(seconds, label="seconds")

    if _use_db_backend():
        now = _now()
        upsert_state("locked_key", key_clean, now + seconds_clean)
        insert_lock_history(key_clean)
        _prune_db_if_needed(now)
        return

    _memory_lock_key(key_clean, seconds_clean)


def is_key_locked(key: str) -> bool:
    key_clean = _require_text(key, label="key")

    if _use_db_backend():
        until = get_active_state_until("locked_key", key_clean)
        return until is not None and until > _now()

    return _memory_is_key_locked(key_clean)


def get_key_lock_seconds_remaining(key: str) -> int:
    key_clean = _require_text(key, label="key")

    if _use_db_backend():
        until = get_active_state_until("locked_key", key_clean)
        if until is None:
            return 0
        return max(0, int(until - _now()))

    return _memory_get_key_lock_seconds_remaining(key_clean)


def get_progressive_lock_seconds(key: str) -> int:
    key_clean = _require_text(key, label="key")

    if _use_db_backend():
        count = recent_lock_count(key_clean, _PROGRESSIVE_LOCK_LOOKBACK_SECONDS)

        if count >= 2:
            return _MAX_PROGRESSIVE_LOCK_SECONDS

        if count >= 1:
            return _ESCALATED_PROGRESSIVE_LOCK_SECONDS

        return _DEFAULT_PROGRESSIVE_LOCK_SECONDS

    return _memory_get_progressive_lock_seconds(key_clean)


def is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    key_clean = _require_text(key, label="key")
    limit_clean = _require_positive_int(limit, label="limit")
    window_clean = _require_positive_int(window_seconds, label="window_seconds")

    if _use_db_backend():
        _ensure_db_tables()
        now = _now()

        insert_rate_limit_event(key_clean)
        count = count_rate_limit_events(key_clean, window_clean)

        _prune_db_if_needed(now)
        return count > limit_clean

    return _memory_is_rate_limited(key_clean, limit_clean, window_clean)


def get_banned_ips_snapshot() -> list[dict[str, int | str]]:
    if _use_db_backend():
        rows = get_active_state_rows("banned_ip")
        return [
            {
                "ip": row["key"],
                "seconds_remaining": row["seconds_remaining"],
                "banned_until_epoch": row["until_epoch"],
            }
            for row in rows
        ]

    with _STATE_LOCK:
        now = _now()
        _prune_expired_state(_BANNED_IPS, now)

        rows: list[dict[str, int | str]] = []
        for ip, until in sorted(
            _BANNED_IPS.items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            rows.append(
                {
                    "ip": ip,
                    "seconds_remaining": max(0, int(until - now)),
                    "banned_until_epoch": int(until),
                }
            )

        return rows


def get_rate_limit_snapshot(window_seconds: int = 3600) -> list[dict[str, int | str]]:
    window_clean = _require_positive_int(window_seconds, label="window_seconds")

    if _use_db_backend():
        _ensure_db_tables()
        _prune_db_if_needed(_now())
        return get_rate_limit_snapshot_rows(window_clean)

    with _STATE_LOCK:
        now = _now()
        rows: list[dict[str, int | str]] = []
        empty_keys: list[str] = []

        for key, bucket in _BUCKETS.items():
            _prune_bucket(bucket, window_clean, now)

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
    if _use_db_backend():
        rows = get_active_state_rows("locked_key")
        return [
            {
                "key": row["key"],
                "seconds_remaining": row["seconds_remaining"],
                "locked_until_epoch": row["until_epoch"],
            }
            for row in rows
        ]

    with _STATE_LOCK:
        now = _now()
        _prune_expired_state(_LOCKED_KEYS, now)

        rows: list[dict[str, int | str]] = []
        for key, until in sorted(
            _LOCKED_KEYS.items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            rows.append(
                {
                    "key": key,
                    "seconds_remaining": max(0, int(until - now)),
                    "locked_until_epoch": int(until),
                }
            )

        return rows
