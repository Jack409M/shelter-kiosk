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


def ensure_indexes() -> None:
    # Fast lookup for active and historical enrollments by resident
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


def ensure_tables(kind: str) -> None:
    ensure_program_enrollments_table(kind)
