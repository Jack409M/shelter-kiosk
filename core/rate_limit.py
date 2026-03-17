from __future__ import annotations

import time
from collections import deque
from threading import RLock

from flask import current_app, g, has_app_context

from core.db import db_execute, db_fetchall


_BUCKETS: dict[str, deque[float]] = {}
_BANNED_IPS: dict[str, float] = {}
_LOCKED_KEYS: dict[str, float] = {}
_LOCK_HISTORY: dict[str, deque[float]] = {}
_STATE_LOCK = RLock()


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

    if current_app.config.get("_RATE_LIMIT_DB_READY") is True:
        return

    kind = _db_kind()
    if kind not in {"pg", "sqlite"}:
        return

    if kind == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS security_runtime_state (
                state_type TEXT NOT NULL,
                state_key TEXT NOT NULL,
                expires_at_epoch DOUBLE PRECISION NOT NULL,
                created_at_epoch DOUBLE PRECISION NOT NULL,
                updated_at_epoch DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (state_type, state_key)
            )
            """
        )
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS security_lock_history (
                state_key TEXT NOT NULL,
                created_at_epoch DOUBLE PRECISION NOT NULL
            )
            """
        )
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS security_runtime_state_type_exp_idx
            ON security_runtime_state (state_type, expires_at_epoch)
            """
        )
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS security_lock_history_key_created_idx
            ON security_lock_history (state_key, created_at_epoch)
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS security_runtime_state (
                state_type TEXT NOT NULL,
                state_key TEXT NOT NULL,
                expires_at_epoch REAL NOT NULL,
                created_at_epoch REAL NOT NULL,
                updated_at_epoch REAL NOT NULL,
                PRIMARY KEY (state_type, state_key)
            )
            """
        )
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS security_lock_history (
                state_key TEXT NOT NULL,
                created_at_epoch REAL NOT NULL
            )
            """
        )
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS security_runtime_state_type_exp_idx
            ON security_runtime_state (state_type, expires_at_epoch)
            """
        )
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS security_lock_history_key_created_idx
            ON security_lock_history (state_key, created_at_epoch)
            """
        )

    current_app.config["_RATE_LIMIT_DB_READY"] = True


def _db_prune_if_needed(now: float) -> None:
    if not has_app_context():
        return

    last_prune = float(current_app.config.get("_RATE_LIMIT_DB_LAST_PRUNE_TS", 0.0) or 0.0)
    if now - last_prune < 600:
        return

    current_app.config["_RATE_LIMIT_DB_LAST_PRUNE_TS"] = now
    kind = _db_kind()

    try:
        if kind == "pg":
            db_execute(
                """
                DELETE FROM security_runtime_state
                WHERE expires_at_epoch <= %s
                """,
                (now,),
            )
            db_execute(
                """
                DELETE FROM security_lock_history
                WHERE created_at_epoch < %s
                """,
                (now - 86400,),
            )
            db_execute(
                """
                DELETE FROM rate_limit_events
                WHERE created_at < NOW() - INTERVAL '2 days'
                """
            )
        elif kind == "sqlite":
            db_execute(
                """
                DELETE FROM security_runtime_state
                WHERE expires_at_epoch <= ?
                """,
                (now,),
            )
            db_execute(
                """
                DELETE FROM security_lock_history
                WHERE created_at_epoch < ?
                """,
                (now - 86400,),
            )
            db_execute(
                """
                DELETE FROM rate_limit_events
                WHERE created_at < datetime('now', '-2 days')
                """
            )
    except Exception:
        pass


def _db_upsert_state(state_type: str, state_key: str, expires_at_epoch: float) -> None:
    _ensure_db_tables()
    now = time.time()
    kind = _db_kind()

    if kind == "pg":
        db_execute(
            """
            INSERT INTO security_runtime_state (
                state_type,
                state_key,
                expires_at_epoch,
                created_at_epoch,
                updated_at_epoch
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (state_type, state_key)
            DO UPDATE SET
                expires_at_epoch = EXCLUDED.expires_at_epoch,
                updated_at_epoch = EXCLUDED.updated_at_epoch
            """,
            (state_type, state_key, expires_at_epoch, now, now),
        )
    else:
        db_execute(
            """
            INSERT INTO security_runtime_state (
                state_type,
                state_key,
                expires_at_epoch,
                created_at_epoch,
                updated_at_epoch
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(state_type, state_key)
            DO UPDATE SET
                expires_at_epoch = excluded.expires_at_epoch,
                updated_at_epoch = excluded.updated_at_epoch
            """,
            (state_type, state_key, expires_at_epoch, now, now),
        )


def _db_get_active_state_until(state_type: str, state_key: str) -> float | None:
    _ensure_db_tables()
    now = time.time()
    _db_prune_if_needed(now)
    kind = _db_kind()

    rows = db_fetchall(
        """
        SELECT expires_at_epoch
        FROM security_runtime_state
        WHERE state_type = %s
          AND state_key = %s
          AND expires_at_epoch > %s
        LIMIT 1
        """
        if kind == "pg"
        else """
        SELECT expires_at_epoch
        FROM security_runtime_state
        WHERE state_type = ?
          AND state_key = ?
          AND expires_at_epoch > ?
        LIMIT 1
        """,
        (state_type, state_key, now),
    )

    if not rows:
        return None

    row = rows[0]
    if isinstance(row, dict):
        return float(row.get("expires_at_epoch"))
    return float(row[0])


def _db_insert_lock_history(state_key: str) -> None:
    _ensure_db_tables()
    now = time.time()
    kind = _db_kind()

    db_execute(
        """
        INSERT INTO security_lock_history (state_key, created_at_epoch)
        VALUES (%s, %s)
        """
        if kind == "pg"
        else """
        INSERT INTO security_lock_history (state_key, created_at_epoch)
        VALUES (?, ?)
        """,
        (state_key, now),
    )


def _db_recent_lock_count(state_key: str, window_seconds: int) -> int:
    _ensure_db_tables()
    now = time.time()
    cutoff = now - window_seconds
    kind = _db_kind()

    rows = db_fetchall(
        """
        SELECT COUNT(1) AS c
        FROM security_lock_history
        WHERE state_key = %s
          AND created_at_epoch >= %s
        """
        if kind == "pg"
        else """
        SELECT COUNT(1) AS c
        FROM security_lock_history
        WHERE state_key = ?
          AND created_at_epoch >= ?
        """,
        (state_key, cutoff),
    )

    if not rows:
        return 0

    row = rows[0]
    if isinstance(row, dict):
        return int(row.get("c", 0) or 0)
    return int(row[0] or 0)


def _memory_ban_ip(ip: str, seconds: int) -> None:
    with _STATE_LOCK:
        _BANNED_IPS[ip] = time.time() + seconds


def _memory_is_ip_banned(ip: str) -> bool:
    with _STATE_LOCK:
        now = time.time()
        _prune_expired_bans(now)

        until = _BANNED_IPS.get(ip)
        if until is None:
            return False

        return until > now


def _memory_lock_key(key: str, seconds: int) -> None:
    with _STATE_LOCK:
        now = time.time()
        _LOCKED_KEYS[key] = now + seconds

        history = _LOCK_HISTORY.get(key)
        if history is None:
            history = deque()
            _LOCK_HISTORY[key] = history

        history.append(now)
        _prune_bucket(history, 86400, now)


def _memory_is_key_locked(key: str) -> bool:
    with _STATE_LOCK:
        now = time.time()
        _prune_expired_locks(now)

        until = _LOCKED_KEYS.get(key)
        if until is None:
            return False

        return until > now


def _memory_get_key_lock_seconds_remaining(key: str) -> int:
    with _STATE_LOCK:
        now = time.time()
        _prune_expired_locks(now)

        until = _LOCKED_KEYS.get(key)
        if until is None:
            return 0

        return max(0, int(until - now))


def _memory_get_progressive_lock_seconds(key: str) -> int:
    with _STATE_LOCK:
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

        if recent_lock_count_30m >= 2:
            return 10800

        if recent_lock_count_30m >= 1:
            return 1800

        return 600


def _memory_is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    with _STATE_LOCK:
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


def ban_ip(ip: str, seconds: int) -> None:
    if _use_db_backend():
        expires_at_epoch = time.time() + seconds
        _db_upsert_state("banned_ip", ip, expires_at_epoch)
        _db_prune_if_needed(time.time())
        return

    _memory_ban_ip(ip, seconds)


def is_ip_banned(ip: str) -> bool:
    if _use_db_backend():
        until = _db_get_active_state_until("banned_ip", ip)
        return until is not None and until > time.time()

    return _memory_is_ip_banned(ip)


def lock_key(key: str, seconds: int) -> None:
    if _use_db_backend():
        now = time.time()
        _db_upsert_state("locked_key", key, now + seconds)
        _db_insert_lock_history(key)
        _db_prune_if_needed(now)
        return

    _memory_lock_key(key, seconds)


def is_key_locked(key: str) -> bool:
    if _use_db_backend():
        until = _db_get_active_state_until("locked_key", key)
        return until is not None and until > time.time()

    return _memory_is_key_locked(key)


def get_key_lock_seconds_remaining(key: str) -> int:
    if _use_db_backend():
        until = _db_get_active_state_until("locked_key", key)
        if until is None:
            return 0
        return max(0, int(until - time.time()))

    return _memory_get_key_lock_seconds_remaining(key)


def get_progressive_lock_seconds(key: str) -> int:
    if _use_db_backend():
        recent_lock_count_30m = _db_recent_lock_count(key, 1800)

        if recent_lock_count_30m >= 2:
            return 10800

        if recent_lock_count_30m >= 1:
            return 1800

        return 600

    return _memory_get_progressive_lock_seconds(key)


def is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    if _use_db_backend():
        _ensure_db_tables()

        if limit <= 0 or window_seconds <= 0:
            return True

        kind = _db_kind()
        now = time.time()

        db_execute(
            "INSERT INTO rate_limit_events (k) VALUES (%s)"
            if kind == "pg"
            else "INSERT INTO rate_limit_events (k) VALUES (?)",
            (key,),
        )

        rows = db_fetchall(
            """
            SELECT COUNT(1) AS c
            FROM rate_limit_events
            WHERE k = %s
              AND created_at >= NOW() - (%s * INTERVAL '1 second')
            """
            if kind == "pg"
            else """
            SELECT COUNT(1) AS c
            FROM rate_limit_events
            WHERE k = ?
              AND created_at >= datetime('now', '-' || ? || ' seconds')
            """,
            (key, window_seconds),
        )

        count = 0
        if rows:
            row = rows[0]
            count = int(row["c"] if isinstance(row, dict) else row[0])

        _db_prune_if_needed(now)
        return count > limit

    return _memory_is_rate_limited(key, limit, window_seconds)


def get_banned_ips_snapshot() -> list[dict[str, int | str]]:
    if _use_db_backend():
        _ensure_db_tables()
        now = time.time()
        _db_prune_if_needed(now)
        kind = _db_kind()

        rows = db_fetchall(
            """
            SELECT state_key, expires_at_epoch
            FROM security_runtime_state
            WHERE state_type = %s
              AND expires_at_epoch > %s
            ORDER BY expires_at_epoch DESC
            """
            if kind == "pg"
            else """
            SELECT state_key, expires_at_epoch
            FROM security_runtime_state
            WHERE state_type = ?
              AND expires_at_epoch > ?
            ORDER BY expires_at_epoch DESC
            """,
            ("banned_ip", now),
        )

        out: list[dict[str, int | str]] = []
        for row in rows or []:
            ip = row["state_key"] if isinstance(row, dict) else row[0]
            until = float(row["expires_at_epoch"] if isinstance(row, dict) else row[1])
            out.append(
                {
                    "ip": str(ip),
                    "seconds_remaining": max(0, int(until - now)),
                    "banned_until_epoch": int(until),
                }
            )

        return out

    with _STATE_LOCK:
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
    if _use_db_backend():
        _ensure_db_tables()
        _db_prune_if_needed(time.time())
        kind = _db_kind()

        rows = db_fetchall(
            """
            SELECT
                k AS key,
                COUNT(1) AS hits,
                MIN(EXTRACT(EPOCH FROM created_at))::bigint AS oldest_epoch,
                MAX(EXTRACT(EPOCH FROM created_at))::bigint AS newest_epoch
            FROM rate_limit_events
            WHERE created_at >= NOW() - (%s * INTERVAL '1 second')
            GROUP BY k
            ORDER BY COUNT(1) DESC, k ASC
            """
            if kind == "pg"
            else """
            SELECT
                k AS key,
                COUNT(1) AS hits,
                CAST(MIN(strftime('%s', created_at)) AS INTEGER) AS oldest_epoch,
                CAST(MAX(strftime('%s', created_at)) AS INTEGER) AS newest_epoch
            FROM rate_limit_events
            WHERE created_at >= datetime('now', '-' || ? || ' seconds')
            GROUP BY k
            ORDER BY COUNT(1) DESC, k ASC
            """,
            (window_seconds,),
        )

        out: list[dict[str, int | str]] = []
        for row in rows or []:
            out.append(
                {
                    "key": row["key"] if isinstance(row, dict) else row[0],
                    "hits": int(row["hits"] if isinstance(row, dict) else row[1]),
                    "oldest_epoch": int(row["oldest_epoch"] if isinstance(row, dict) else row[2]),
                    "newest_epoch": int(row["newest_epoch"] if isinstance(row, dict) else row[3]),
                }
            )

        return out

    with _STATE_LOCK:
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
    if _use_db_backend():
        _ensure_db_tables()
        now = time.time()
        _db_prune_if_needed(now)
        kind = _db_kind()

        rows = db_fetchall(
            """
            SELECT state_key, expires_at_epoch
            FROM security_runtime_state
            WHERE state_type = %s
              AND expires_at_epoch > %s
            ORDER BY expires_at_epoch DESC
            """
            if kind == "pg"
            else """
            SELECT state_key, expires_at_epoch
            FROM security_runtime_state
            WHERE state_type = ?
              AND expires_at_epoch > ?
            ORDER BY expires_at_epoch DESC
            """,
            ("locked_key", now),
        )

        out: list[dict[str, int | str]] = []
        for row in rows or []:
            key = row["state_key"] if isinstance(row, dict) else row[0]
            until = float(row["expires_at_epoch"] if isinstance(row, dict) else row[1])
            out.append(
                {
                    "key": str(key),
                    "seconds_remaining": max(0, int(until - now)),
                    "locked_until_epoch": int(until),
                }
            )

        return out

    with _STATE_LOCK:
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
