"""
Flexible resident form intake schema.

Stores raw form submissions so resident submitted forms can change
without breaking the application. Important operational fields can
later be extracted into structured tables for reporting.
"""

from __future__ import annotations

from .schema_helpers import create_table


def ensure_resident_form_submissions_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS resident_form_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER,
            enrollment_id INTEGER,
            form_type TEXT NOT NULL,
            form_source TEXT,
            source_form_id TEXT,
            source_submission_id TEXT,
            submitted_at TEXT,
            raw_payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS resident_form_submissions (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER REFERENCES residents(id),
            enrollment_id INTEGER REFERENCES program_enrollments(id),
            form_type TEXT NOT NULL,
            form_source TEXT,
            source_form_id TEXT,
            source_submission_id TEXT,
            submitted_at TEXT,
            raw_payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


def ensure_weekly_resident_summary_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS weekly_resident_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            submission_id INTEGER,
            week_start TEXT,
            productive_hours REAL,
            work_hours REAL,
            meeting_count INTEGER,
            submitted_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id),
            FOREIGN KEY (submission_id) REFERENCES resident_form_submissions(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS weekly_resident_summary (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            submission_id INTEGER REFERENCES resident_form_submissions(id),
            week_start TEXT,
            productive_hours DOUBLE PRECISION,
            work_hours DOUBLE PRECISION,
            meeting_count INTEGER,
            submitted_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_indexes() -> None:
    try:
        from core.db import db_execute

        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_form_submissions_resident_idx
            ON resident_form_submissions (resident_id)
            """
        )
    except Exception:
        pass

    try:
        from core.db import db_execute

        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_form_submissions_enrollment_idx
            ON resident_form_submissions (enrollment_id)
            """
        )
    except Exception:
        pass

    try:
        from core.db import db_execute

        db_execute(
            """
            CREATE INDEX IF NOT EXISTS weekly_resident_summary_enrollment_idx
            ON weekly_resident_summary (enrollment_id)
            """
        )
    except Exception:
        pass


def ensure_tables(kind: str) -> None:
    ensure_resident_form_submissions_table(kind)
    ensure_weekly_resident_summary_table(kind)
