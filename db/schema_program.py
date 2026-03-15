"""
Program enrollment schema.

This module anchors the new program operations subsystem to the
existing residents table without disturbing current shelter logic.
"""

from __future__ import annotations

from .schema_helpers import create_table


def ensure_program_enrollments_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS program_enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            exit_date TEXT,
            program_status TEXT NOT NULL DEFAULT 'active',
            case_manager_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS program_enrollments (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            shelter TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            exit_date TEXT,
            program_status TEXT NOT NULL DEFAULT 'active',
            case_manager_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_user_dashboard_favorites_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS user_dashboard_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            dashboard_key TEXT NOT NULL,
            metric_key TEXT NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES staff_users(id),
            UNIQUE (user_id, dashboard_key, metric_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_dashboard_favorites (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES staff_users(id),
            dashboard_key TEXT NOT NULL,
            metric_key TEXT NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE (user_id, dashboard_key, metric_key)
        )
        """,
    )


def ensure_indexes() -> None:
    try:
        from core.db import db_execute

        db_execute(
            "CREATE INDEX IF NOT EXISTS program_enrollments_resident_idx "
            "ON program_enrollments (resident_id)"
        )
    except Exception:
        pass

    try:
        from core.db import db_execute

        db_execute(
            "CREATE INDEX IF NOT EXISTS program_enrollments_status_idx "
            "ON program_enrollments (program_status, entry_date)"
        )
    except Exception:
        pass

    try:
        from core.db import db_execute

        db_execute(
            "CREATE INDEX IF NOT EXISTS user_dashboard_favorites_user_dashboard_idx "
            "ON user_dashboard_favorites (user_id, dashboard_key, display_order)"
        )
    except Exception:
        pass

    try:
        from core.db import db_execute

        db_execute(
            "CREATE INDEX IF NOT EXISTS user_dashboard_favorites_metric_idx "
            "ON user_dashboard_favorites (dashboard_key, metric_key)"
        )
    except Exception:
        pass


def ensure_tables(kind: str) -> None:
    ensure_program_enrollments_table(kind)
    ensure_user_dashboard_favorites_table(kind)
    ensure_indexes()
