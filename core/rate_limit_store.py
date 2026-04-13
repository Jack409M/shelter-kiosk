from __future__ import annotations

import time
from typing import Any, Final

from flask import current_app, g, has_app_context

from core.db import db_execute, db_fetchall


_TABLE_READY_FLAG: Final[str] = "_RATE_LIMIT_STORE_READY"


def _now() -> float:
    return time.time()


def _require_db_kind() -> str:
    if not has_app_context():
        raise RuntimeError("rate_limit_store requires app context")

    kind_value = g.get("db_kind")
    if not kind_value:
        raise RuntimeError("db_kind is not set in flask.g")

    kind = str(kind_value).strip().lower()
    if kind not in {"pg", "sqlite"}:
        raise RuntimeError(f"Unsupported db_kind: {kind!r}")

    return kind


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if _require_db_kind() == "pg" else sqlite_sql


def _require_text(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    return text


def _require_positive_int(value: Any, *, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as err:
        raise ValueError(f"{label} must be an integer") from err

    if number <= 0:
        raise ValueError(f"{label} must be positive")

    return number


def ensure_tables() -> None:
    if current_app.config.get(_TABLE_READY_FLAG) is True:
        return

    _require_db_kind()

    db_execute(
        _sql(
            """
            CREATE TABLE IF NOT EXISTS security_lock_history (
                state_key TEXT NOT NULL,
                created_at_epoch DOUBLE PRECISION NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS security_lock_history (
                state_key TEXT NOT NULL,
                created_at_epoch REAL NOT NULL
            )
            """,
        )
    )

    db_execute(
        _sql(
            """
            CREATE TABLE IF NOT EXISTS rate_limit_events (
                id SERIAL PRIMARY KEY,
                k TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS rate_limit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                k TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
    )

    db_execute(
        """
        CREATE INDEX IF NOT EXISTS security_lock_history_key_created_idx
        ON security_lock_history (state_key, created_at_epoch)
        """
    )

    db_execute(
        """
        CREATE INDEX IF NOT EXISTS rate_limit_events_k_created_idx
        ON rate_limit_events (k, created_at)
        """
    )

    db_execute(
        """
        CREATE INDEX IF NOT EXISTS rate_limit_events_created_idx
        ON rate_limit_events (created_at)
        """
    )

    current_app.config[_TABLE_READY_FLAG] = True


def prune_if_needed(now: float) -> None:
    if not has_app_context():
        raise RuntimeError("prune_if_needed requires app context")

    now_clean = float(now)

    last_prune = float(current_app.config.get("_RATE_LIMIT_DB_LAST_PRUNE_TS", 0.0) or 0.0)
    if now_clean - last_prune < 600:
        return

    current_app.config["_RATE_LIMIT_DB_LAST_PRUNE_TS"] = now_clean

    try:
        db_execute(
            _sql(
                """
                DELETE FROM security_lock_history
                WHERE created_at_epoch < %s
                """,
                """
                DELETE FROM security_lock_history
                WHERE created_at_epoch < ?
                """,
            ),
            (now_clean - 86400,),
        )

        db_execute(
            _sql(
                """
                DELETE FROM rate_limit_events
                WHERE created_at < NOW() - INTERVAL '2 days'
                """,
                """
                DELETE FROM rate_limit_events
                WHERE created_at < datetime('now', '-2 days')
                """,
            )
        )

    except Exception as exc:
        current_app.logger.exception(
            "Rate limit prune failed: %s",
            exc,
        )
        raise


def insert_lock_history(state_key: str) -> None:
    ensure_tables()

    key_clean = _require_text(state_key, label="state_key")
    now = _now()

    db_execute(
        _sql(
            """
            INSERT INTO security_lock_history (state_key, created_at_epoch)
            VALUES (%s, %s)
            """,
            """
            INSERT INTO security_lock_history (state_key, created_at_epoch)
            VALUES (?, ?)
            """,
        ),
        (key_clean, now),
    )


def recent_lock_count(state_key: str, window_seconds: int) -> int:
    ensure_tables()

    key_clean = _require_text(state_key, label="state_key")
    window_clean = _require_positive_int(window_seconds, label="window_seconds")

    cutoff = _now() - window_clean

    rows = db_fetchall(
        _sql(
            """
            SELECT COUNT(1) AS c
            FROM security_lock_history
            WHERE state_key = %s
              AND created_at_epoch >= %s
            """,
            """
            SELECT COUNT(1) AS c
            FROM security_lock_history
            WHERE state_key = ?
              AND created_at_epoch >= ?
            """,
        ),
        (key_clean, cutoff),
    )

    if not rows:
        return 0

    row = rows[0]
    value = row.get("c") if isinstance(row, dict) else row[0]

    return int(value or 0)


def insert_rate_limit_event(key: str) -> None:
    ensure_tables()

    key_clean = _require_text(key, label="key")

    db_execute(
        _sql(
            "INSERT INTO rate_limit_events (k) VALUES (%s)",
            "INSERT INTO rate_limit_events (k) VALUES (?)",
        ),
        (key_clean,),
    )


def count_rate_limit_events(key: str, window_seconds: int) -> int:
    ensure_tables()

    key_clean = _require_text(key, label="key")
    window_clean = _require_positive_int(window_seconds, label="window_seconds")

    rows = db_fetchall(
        _sql(
            """
            SELECT COUNT(1) AS c
            FROM rate_limit_events
            WHERE k = %s
              AND created_at >= NOW() - (%s * INTERVAL '1 second')
            """,
            """
            SELECT COUNT(1) AS c
            FROM rate_limit_events
            WHERE k = ?
              AND created_at >= datetime('now', '-' || ? || ' seconds')
            """,
        ),
        (key_clean, window_clean),
    )

    if not rows:
        return 0

    row = rows[0]
    value = row.get("c") if isinstance(row, dict) else row[0]

    return int(value or 0)


def get_rate_limit_snapshot_rows(window_seconds: int) -> list[dict[str, int | str]]:
    ensure_tables()

    window_clean = _require_positive_int(window_seconds, label="window_seconds")

    rows = db_fetchall(
        _sql(
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
            """,
            """
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
        ),
        (window_clean,),
    )

    output: list[dict[str, int | str]] = []

    for row in rows or []:
        key = row.get("key") if isinstance(row, dict) else row[0]
        hits = row.get("hits") if isinstance(row, dict) else row[1]
        oldest = row.get("oldest_epoch") if isinstance(row, dict) else row[2]
        newest = row.get("newest_epoch") if isinstance(row, dict) else row[3]

        try:
            output.append(
                {
                    "key": str(key),
                    "hits": int(hits),
                    "oldest_epoch": int(oldest),
                    "newest_epoch": int(newest),
                }
            )
        except (TypeError, ValueError):
            continue

    return output
