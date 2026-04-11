from __future__ import annotations

import time
from collections import deque
from threading import RLock

from flask import has_app_context, g

from core.rate_limit_store import count_rate_limit_events
from core.rate_limit_store import ensure_tables as ensure_rate_limit_store_tables
from core.rate_limit_store import get_rate_limit_snapshot_rows
from core.rate_limit_store import insert_lock_history
from core.rate_limit_store import insert_rate_limit_event
from core.rate_limit_store import prune_if_needed as prune_rate_limit_store_if_needed
from core.rate_limit_store import recent_lock_count
from core.security_state_store import ensure_tables as ensure_security_state_tables
from core.security_state_store import get_active_state_until
from core.security_state_store import upsert_state


_BUCKETS: dict[str, deque[float]] = {}
_BANNED_IPS: dict[str, float] = {}
_LOCKED_KEYS: dict[str, float] = {}
_LOCK_HISTORY: dict[str, deque[float]] = {}
_STATE_LOCK = RLock()


def _now() -> float:
    return time.time()


def _prune_bucket(bucket: deque[float], window_seconds: int, now: float) -> None:
    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def _prune_expired_state(state: dict[str, float], now: float) -> None:
    expired_keys = [key for key, until in state.items() if until <= now]
    for key in expired_keys:
        del state[key]


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


def _db_kind() -> str:
    if not has_app_context():
        return ""
    try:
        return str(g.get("db_kind") or "").strip().lower()
    except Exception:
        return ""


def _use_db_backend() -> bool:
    return _db_kind() in {"pg", "sqlite"}


def _ensure_db_tables() -> None:
    if not has_app_context():
        return

    ensure_security_state_tables()
    ensure_rate_limit_store_tables()


def _prune_db_if_needed(now: float) -> None:
    if not has_app_context():
        return
    prune_rate_limit_store_if_needed(now)


def _db_fetch_active_state_rows(state_type: str) -> list[dict[str, int | str]]:
    now = _now()
    rows: list[dict[str, int | str]] = []

    for state_key, until in []:
        pass

    from core.db import db_fetchall

    rows_raw = db_fetchall(
        """
        SELECT state_key, expires_at_epoch
        FROM security_runtime_state
        WHERE state_type = ?
          AND expires_at_epoch > ?
        ORDER BY expires_at_epoch DESC
        """
        if _db_kind() == "sqlite"
        else """
        SELECT state_key, expires_at_epoch
        FROM security_runtime_state
        WHERE state_type = %s
          AND expires_at_epoch > %s
        ORDER BY expires_at_epoch DESC
        """,
        (state_type, now),
    )

    output: list[dict[str, int | str]] = []
    for row in rows_raw or []:
        key = row.get("state_key") if isinstance(row, dict) else row[0]
        until = float(row.get("expires_at_epoch") if isinstance(row, dict) else row[1])
        output.append(
            {
                "key": str(key),
                "seconds_remaining": max(0, int(until - now)),
                "until_epoch": int(until),
            }
        )

    return output


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
        _prune_bucket(history, 86400, now)


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
            return 600

        cutoff_30m = now - 1800
        recent_lock_count_30m = sum(1 for ts in history if ts >= cutoff_30m)

        if recent_lock_count_30m >= 2:
            return 10800

        if recent_lock_count_30m >= 1:
            return 1800

        return 600


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
    if _use_db_backend():
        upsert_state("banned_ip", ip, _now() + seconds)
        _prune_db_if_needed(_now())
        return

    _memory_ban_ip(ip, seconds)


def is_ip_banned(ip: str) -> bool:
    if _use_db_backend():
        until = get_active_state_until("banned_ip", ip)
        return until is not None and until > _now()

    return _memory_is_ip_banned(ip)


def lock_key(key: str, seconds: int) -> None:
    if _use_db_backend():
        now = _now()
        upsert_state("locked_key", key, now + seconds)
        insert_lock_history(key)
        _prune_db_if_needed(now)
        return

    _memory_lock_key(key, seconds)


def is_key_locked(key: str) -> bool:
    if _use_db_backend():
        until = get_active_state_until("locked_key", key)
        return until is not None and until > _now()

    return _memory_is_key_locked(key)


def get_key_lock_seconds_remaining(key: str) -> int:
    if _use_db_backend():
        until = get_active_state_until("locked_key", key)
        if until is None:
            return 0
        return max(0, int(until - _now()))

    return _memory_get_key_lock_seconds_remaining(key)


def get_progressive_lock_seconds(key: str) -> int:
    if _use_db_backend():
        count = recent_lock_count(key, 1800)

        if count >= 2:
            return 10800

        if count >= 1:
            return 1800

        return 600

    return _memory_get_progressive_lock_seconds(key)


def is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    if limit <= 0 or window_seconds <= 0:
        return True

    if _use_db_backend():
        _ensure_db_tables()
        now = _now()

        insert_rate_limit_event(key)
        count = count_rate_limit_events(key, window_seconds)

        _prune_db_if_needed(now)
        return count > limit

    return _memory_is_rate_limited(key, limit, window_seconds)


def get_banned_ips_snapshot() -> list[dict[str, int | str]]:
    if _use_db_backend():
        rows = _db_fetch_active_state_rows("banned_ip")
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
        for ip, until in sorted(_BANNED_IPS.items(), key=lambda item: item[1], reverse=True):
            rows.append(
                {
                    "ip": ip,
                    "seconds_remaining": max(0, int(until - now)),
                    "banned_until_epoch": int(until),
                }
            )

        return rows


def get_rate_limit_snapshot(window_seconds: int = 3600) -> list[dict[str, int | str]]:
    if _use_db_backend():
        _ensure_db_tables()
        _prune_db_if_needed(_now())
        return get_rate_limit_snapshot_rows(window_seconds)

    with _STATE_LOCK:
        now = _now()
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
    if _use_db_backend():
        rows = _db_fetch_active_state_rows("locked_key")
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
        for key, until in sorted(_LOCKED_KEYS.items(), key=lambda item: item[1], reverse=True):
            rows.append(
                {
                    "key": key,
                    "seconds_remaining": max(0, int(until - now)),
                    "locked_until_epoch": int(until),
                }
            )

        return rows
