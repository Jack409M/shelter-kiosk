"""
Case management schema.

Tracks structured case manager interactions with residents
during program participation.
"""

from __future__ import annotations

from core.db import db_execute

from .schema_helpers import create_table


def ensure_case_manager_updates_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS case_manager_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            staff_user_id INTEGER NOT NULL,
            meeting_date TEXT NOT NULL,
            notes TEXT,
            progress_notes TEXT,
            action_items TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS case_manager_updates (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            staff_user_id INTEGER NOT NULL,
            meeting_date TEXT NOT NULL,
            notes TEXT,
            progress_notes TEXT,
            action_items TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_indexes() -> None:
    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS case_manager_updates_enrollment_idx
            ON case_manager_updates (enrollment_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS case_manager_updates_staff_idx
            ON case_manager_updates (staff_user_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS case_manager_updates_enrollment_meeting_idx
            ON case_manager_updates (enrollment_id, meeting_date)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS case_manager_updates_staff_meeting_idx
            ON case_manager_updates (staff_user_id, meeting_date)
            """
        )
    except Exception:
        pass


def ensure_tables(kind: str) -> None:
    ensure_case_manager_updates_table(kind)
