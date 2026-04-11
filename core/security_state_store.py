from __future__ import annotations

import time
from typing import Any

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

    if current_app.config.get("_SECURITY_STATE_READY") is True:
        return

    kind = _db_kind()
    if kind not in {"pg", "sqlite"}:
        return

    db_execute(
        _sql(
            """
            CREATE TABLE IF NOT EXISTS security_runtime_state (
                state_type TEXT NOT NULL,
                state_key TEXT NOT NULL,
                expires_at_epoch DOUBLE PRECISION NOT NULL,
                created_at_epoch DOUBLE PRECISION NOT NULL,
                updated_at_epoch DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (state_type, state_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS security_runtime_state (
                state_type TEXT NOT NULL,
                state_key TEXT NOT NULL,
                expires_at_epoch REAL NOT NULL,
                created_at_epoch REAL NOT NULL,
                updated_at_epoch REAL NOT NULL,
                PRIMARY KEY (state_type, state_key)
            )
            """,
        )
    )

    db_execute(
        """
        CREATE INDEX IF NOT EXISTS security_runtime_state_type_exp_idx
        ON security_runtime_state (state_type, expires_at_epoch)
        """
    )

    current_app.config["_SECURITY_STATE_READY"] = True


def upsert_state(state_type: str, key: str, expires_at: float) -> None:
    ensure_tables()
    now = _now()

    db_execute(
        _sql(
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
        ),
        (state_type, key, expires_at, now, now),
    )


def get_active_state_until(state_type: str, key: str) -> float | None:
    ensure_tables()
    now = _now()

    rows = db_fetchall(
        _sql(
            """
            SELECT expires_at_epoch
            FROM security_runtime_state
            WHERE state_type = %s
              AND state_key = %s
              AND expires_at_epoch > %s
            LIMIT 1
            """,
            """
            SELECT expires_at_epoch
            FROM security_runtime_state
            WHERE state_type = ?
              AND state_key = ?
              AND expires_at_epoch > ?
            LIMIT 1
            """,
        ),
        (state_type, key, now),
    )

    if not rows:
        return None

    row = rows[0]
    return float(row.get("expires_at_epoch") if isinstance(row, dict) else row[0])


def get_active_state_rows(state_type: str) -> list[dict[str, int | str]]:
    ensure_tables()
    now = _now()

    rows = db_fetchall(
        _sql(
            """
            SELECT state_key, expires_at_epoch
            FROM security_runtime_state
            WHERE state_type = %s
              AND expires_at_epoch > %s
            ORDER BY expires_at_epoch DESC
            """,
            """
            SELECT state_key, expires_at_epoch
            FROM security_runtime_state
            WHERE state_type = ?
              AND expires_at_epoch > ?
            ORDER BY expires_at_epoch DESC
            """,
        ),
        (state_type, now),
    )

    output: list[dict[str, int | str]] = []

    for row in rows or []:
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
