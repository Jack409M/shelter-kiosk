from __future__ import annotations

from core.db import db_execute

from .schema_helpers import create_table


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


def ensure_calendar_indexes() -> None:
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


def ensure_tables(kind: str) -> None:
    ensure_case_manager_calendar_events_table(kind)
    ensure_calendar_indexes()
