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


def ensure_case_manager_calendar_events_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS case_manager_calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            event_date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            shelter TEXT,
            staff_user_id INTEGER NOT NULL,
            notes TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS case_manager_calendar_events (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            event_date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            shelter TEXT,
            staff_user_id INTEGER NOT NULL,
            notes TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_intake_drafts_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS intake_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            resident_name TEXT,
            entry_date TEXT,
            form_payload TEXT NOT NULL,
            created_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS intake_drafts (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            resident_name TEXT,
            entry_date TEXT,
            form_payload TEXT NOT NULL,
            created_by_user_id INTEGER,
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

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS case_manager_calendar_events_date_idx
            ON case_manager_calendar_events (event_date)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS case_manager_calendar_events_staff_idx
            ON case_manager_calendar_events (staff_user_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS case_manager_calendar_events_shelter_idx
            ON case_manager_calendar_events (shelter)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS case_manager_calendar_events_staff_date_idx
            ON case_manager_calendar_events (staff_user_id, event_date)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS case_manager_calendar_events_shelter_date_idx
            ON case_manager_calendar_events (shelter, event_date)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_status_idx
            ON intake_drafts (status)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_shelter_idx
            ON intake_drafts (shelter)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_entry_date_idx
            ON intake_drafts (entry_date)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_shelter_status_updated_idx
            ON intake_drafts (shelter, status, updated_at)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_created_by_idx
            ON intake_drafts (created_by_user_id)
            """
        )
    except Exception:
        pass


def ensure_tables(kind: str) -> None:
    ensure_case_manager_updates_table(kind)
    ensure_case_manager_calendar_events_table(kind)
    ensure_intake_drafts_table(kind)
    ensure_indexes()
