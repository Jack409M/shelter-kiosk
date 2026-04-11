from __future__ import annotations

import time

from flask import current_app, g, has_app_context

from core.db import db_execute, db_fetchall


def _now() -> float:
    return time.time()


def _db_kind() -> str:
    if not has_app_context():
        return ""
    try:
        return str(g.get("db_kind") or "").strip().lower()
    except Exception:
        return ""


def _is_pg() -> bool:
    return _db_kind() == "pg"


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if _is_pg() else sqlite_sql


def ensure_tables() -> None:
    if not has_app_context():
        return

    if current_app.config.get("_RATE_LIMIT_STORE_READY") is True:
        return

    kind = _db_kind()
    if kind not in {"pg", "sqlite"}:
        return

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

    current_app.config["_RATE_LIMIT_STORE_READY"] = True


def prune_if_needed(now: float) -> None:
    if not has_app_context():
        return

    last_prune = float(current_app.config.get("_RATE_LIMIT_DB_LAST_PRUNE_TS", 0.0) or 0.0)
    if now - last_prune < 600:
        return

    current_app.config["_RATE_LIMIT_DB_LAST_PRUNE_TS"] = now

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
            (now - 86400,),
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
    except Exception:
        pass


def insert_lock_history(state_key: str) -> None:
    ensure_tables()
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
        (state_key, now),
    )


def recent_lock_count(state_key: str, window_seconds: int) -> int:
    ensure_tables()
    cutoff = _now() - window_seconds

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
        (state_key, cutoff),
    )

    if not rows:
        return 0

    row = rows[0]
    return int(row.get("c", 0) if isinstance(row, dict) else row[0] or 0)


def insert_rate_limit_event(key: str) -> None:
    ensure_tables()

    db_execute(
        _sql(
            "INSERT INTO rate_limit_events (k) VALUES (%s)",
            "INSERT INTO rate_limit_events (k) VALUES (?)",
        ),
        (key,),
    )


def count_rate_limit_events(key: str, window_seconds: int) -> int:
    ensure_tables()

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
        (key, window_seconds),
    )

    if not rows:
        return 0

    row = rows[0]
    return int(row.get("c", 0) if isinstance(row, dict) else row[0] or 0)


def get_rate_limit_snapshot_rows(window_seconds: int) -> list[dict[str, int | str]]:
    ensure_tables()

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
        (window_seconds,),
    )

    output: list[dict[str, int | str]] = []

    for row in rows or []:
        output.append(
            {
                "key": row.get("key") if isinstance(row, dict) else row[0],
                "hits": int(row.get("hits") if isinstance(row, dict) else row[1]),
                "oldest_epoch": int(row.get("oldest_epoch") if isinstance(row, dict) else row[2]),
                "newest_epoch": int(row.get("newest_epoch") if isinstance(row, dict) else row[3]),
            }
        )

    return output
