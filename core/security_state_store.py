from __future__ import annotations

import time
from typing import Any, Final

from flask import current_app, g, has_app_context

from core.db import db_execute, db_fetchall, db_fetchone

_TABLE_NAME: Final[str] = "security_runtime_state"


def _now() -> float:
    return time.time()


def _require_db_kind() -> str:
    if not has_app_context():
        raise RuntimeError("security_state_store requires app context")

    kind_value = g.get("db_kind")
    if not kind_value:
        raise RuntimeError("db_kind is not set in flask.g")

    kind = str(kind_value).strip().lower()
    if kind not in {"pg", "sqlite"}:
        raise RuntimeError(f"Unsupported db_kind: {kind!r}")

    return kind


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    kind = _require_db_kind()
    return pg_sql if kind == "pg" else sqlite_sql


def _ensure_tables_once() -> None:
    if current_app.config.get("_SECURITY_STATE_READY") is True:
        return

    _require_db_kind()

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


def _require_text(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    return text


def _require_epoch(value: Any, *, label: str) -> float:
    try:
        epoch = float(value)
    except (TypeError, ValueError) as err:
        raise ValueError(f"{label} must be a number") from err

    if epoch <= 0:
        raise ValueError(f"{label} must be positive")

    return epoch


def upsert_state(state_type: str, key: str, expires_at: float) -> None:
    _ensure_tables_once()

    state_type_clean = _require_text(state_type, label="state_type")
    key_clean = _require_text(key, label="state_key")
    expires_at_clean = _require_epoch(expires_at, label="expires_at")

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
        (state_type_clean, key_clean, expires_at_clean, now, now),
    )


def get_active_state_until(state_type: str, key: str) -> float | None:
    _ensure_tables_once()

    state_type_clean = _require_text(state_type, label="state_type")
    key_clean = _require_text(key, label="state_key")

    now = _now()

    row = db_fetchone(
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
        (state_type_clean, key_clean, now),
    )

    if row is None:
        return None

    value = row.get("expires_at_epoch") if isinstance(row, dict) else row[0]

    try:
        return float(value)
    except (TypeError, ValueError):
        current_app.logger.warning(
            "Invalid expires_at_epoch value in security_runtime_state: %r",
            value,
        )
        return None


def get_active_state_rows(state_type: str) -> list[dict[str, int | str]]:
    _ensure_tables_once()

    state_type_clean = _require_text(state_type, label="state_type")
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
        (state_type_clean, now),
    )

    output: list[dict[str, int | str]] = []

    for row in rows or []:
        key = row.get("state_key") if isinstance(row, dict) else row[0]
        until_value = row.get("expires_at_epoch") if isinstance(row, dict) else row[1]

        try:
            until = float(until_value)
        except (TypeError, ValueError):
            continue

        output.append(
            {
                "key": str(key),
                "seconds_remaining": max(0, int(until - now)),
                "until_epoch": int(until),
            }
        )

    return output
