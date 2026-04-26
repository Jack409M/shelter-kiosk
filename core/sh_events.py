from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from flask import current_app, g, has_app_context

from core.db import db_execute, db_fetchone


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _kind() -> str:
    return str(g.get("db_kind") or "").strip().lower()


def _ensure_sh_events_table() -> None:
    kind = _kind()

    if kind == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS sh_events (
                id SERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                event_status TEXT NOT NULL,
                event_source TEXT NOT NULL DEFAULT '',
                entity_type TEXT NOT NULL DEFAULT '',
                entity_id INTEGER,
                shelter TEXT NOT NULL DEFAULT '',
                staff_user_id INTEGER,
                message TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        return

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS sh_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            event_status TEXT NOT NULL,
            event_source TEXT NOT NULL DEFAULT '',
            entity_type TEXT NOT NULL DEFAULT '',
            entity_id INTEGER,
            shelter TEXT NOT NULL DEFAULT '',
            staff_user_id INTEGER,
            message TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )


def log_sh_event(
    *,
    event_type: str,
    event_status: str,
    event_source: str = "",
    entity_type: str = "",
    entity_id: int | None = None,
    shelter: str = "",
    staff_user_id: Any = None,
    message: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    _ensure_sh_events_table()

    staff_id: int | None
    try:
        staff_id = int(staff_user_id) if staff_user_id not in (None, "") else None
    except Exception:
        staff_id = None

    metadata_text = json.dumps(metadata or {}, sort_keys=True)

    db_execute(
        """
        INSERT INTO sh_events (
            event_type,
            event_status,
            event_source,
            entity_type,
            entity_id,
            shelter,
            staff_user_id,
            message,
            metadata,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(event_type or "").strip(),
            str(event_status or "").strip(),
            str(event_source or "").strip(),
            str(entity_type or "").strip(),
            entity_id,
            str(shelter or "").strip(),
            staff_id,
            str(message or "").strip(),
            metadata_text,
            _now_iso(),
        ),
    )


def safe_log_sh_event(**kwargs: Any) -> None:
    try:
        log_sh_event(**kwargs)
    except Exception:
        if has_app_context():
            current_app.logger.exception("system_health_event_logging_failed")


def latest_sh_event_by_status(event_status: str) -> dict[str, Any] | None:
    _ensure_sh_events_table()

    return db_fetchone(
        """
        SELECT
            id,
            event_type,
            event_status,
            event_source,
            entity_type,
            entity_id,
            shelter,
            staff_user_id,
            message,
            metadata,
            created_at
        FROM sh_events
        WHERE event_status = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (str(event_status or "").strip(),),
    )
