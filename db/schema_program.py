"""
Program enrollment schema.

This module anchors the new program operations subsystem to the
existing residents table without disturbing current shelter logic.
"""

from __future__ import annotations

import contextlib

from core.db import db_execute

from .schema_helpers import create_table


def ensure_program_enrollment_columns(kind: str) -> None:
    if kind == "pg":
        statements = [
            "ALTER TABLE program_enrollments ADD COLUMN IF NOT EXISTS rad_complete BOOLEAN",
            "ALTER TABLE program_enrollments ADD COLUMN IF NOT EXISTS rad_completed_date TEXT",
        ]
    else:
        statements = [
            "ALTER TABLE program_enrollments ADD COLUMN rad_complete INTEGER",
            "ALTER TABLE program_enrollments ADD COLUMN rad_completed_date TEXT",
        ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


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
            rad_complete INTEGER,
            rad_completed_date TEXT,
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
            rad_complete BOOLEAN,
            rad_completed_date TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )

    ensure_program_enrollment_columns(kind)


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
    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS program_enrollments_resident_idx "
            "ON program_enrollments (resident_id)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS program_enrollments_status_idx "
            "ON program_enrollments (program_status, entry_date)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS user_dashboard_favorites_user_dashboard_idx "
            "ON user_dashboard_favorites (user_id, dashboard_key, display_order)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS user_dashboard_favorites_metric_idx "
            "ON user_dashboard_favorites (dashboard_key, metric_key)"
        )


def ensure_tables(kind: str) -> None:
    ensure_program_enrollments_table(kind)
    ensure_user_dashboard_favorites_table(kind)
