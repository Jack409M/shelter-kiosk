from __future__ import annotations

import time
from typing import Any

from flask import current_app, has_app_context

from core.db import db_execute, db_fetchall


def _now() -> float:
    return time.time()


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    db_kind = ""
    if has_app_context():
        try:
            from flask import g
            db_kind = str(g.get("db_kind") or "").strip().lower()
        except Exception:
            db_kind = ""

    return pg_sql if db_kind == "pg" else sqlite_sql


def ensure_tables() -> None:
    if not has_app_context():
        return

    if current_app.config.get("_SECURITY_STATE_READY") is True:
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

    current_app.config["_SECURITY_STATE_READY"] = True


def upsert_state(state_type: str, key: str, expires_at: float) -> None:
    ensure_tables()
    now = _now()

    db_execute(
        _sql(
            """
            INSERT INTO security_runtime_state (
                state_type, state_key, expires_at_epoch, created_at_epoch, updated_at_epoch
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (state_type, state_key)
            DO UPDATE SET
                expires_at_epoch = EXCLUDED.expires_at_epoch,
                updated_at_epoch = EXCLUDED.updated_at_epoch
            """,
            """
            INSERT INTO security_runtime_state (
                state_type, state_key, expires_at_epoch, created_at_epoch, updated_at_epoch
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
