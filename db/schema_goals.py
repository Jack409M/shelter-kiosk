"""
Goals and appointments schema.

Tracks resident goals and scheduled appointments tied to
program enrollments.
"""

from __future__ import annotations

from .schema_helpers import create_table


def ensure_goals_table(kind: str) -> None:
    create_table(
        kind,
        # SQLite
        """
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            goal_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            target_date TEXT,
            completed_date TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,
        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS goals (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            goal_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            target_date TEXT,
            completed_date TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_appointments_table(kind: str) -> None:
    create_table(
        kind,
        # SQLite
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            appointment_type TEXT,
            appointment_date TEXT NOT NULL,
            notes TEXT,
            reminder_sent INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,
        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            appointment_type TEXT,
            appointment_date TEXT NOT NULL,
            notes TEXT,
            reminder_sent INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_indexes() -> None:
    try:
        from core.db import db_execute

        db_execute(
            """
            CREATE INDEX IF NOT EXISTS goals_enrollment_idx
            ON goals (enrollment_id)
            """
        )
    except Exception:
        from flask import current_app
        current_app.logger.exception("auto-logged exception")

    try:
        from core.db import db_execute

        db_execute(
            """
            CREATE INDEX IF NOT EXISTS appointments_enrollment_idx
            ON appointments (enrollment_id)
            """
        )
    except Exception:
        from flask import current_app
        current_app.logger.exception("auto-logged exception")


def ensure_tables(kind: str) -> None:
    ensure_goals_table(kind)
    ensure_appointments_table(kind)
