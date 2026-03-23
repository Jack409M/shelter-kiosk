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
            updated_grit INTEGER,
            parenting_class_completed INTEGER,
            warrants_or_fines_paid INTEGER,
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
            updated_grit INTEGER,
            parenting_class_completed INTEGER,
            warrants_or_fines_paid INTEGER,
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


def ensure_client_services_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS client_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            case_manager_update_id INTEGER,
            service_type TEXT NOT NULL,
            service_date TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id),
            FOREIGN KEY (case_manager_update_id) REFERENCES case_manager_updates(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS client_services (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            case_manager_update_id INTEGER REFERENCES case_manager_updates(id),
            service_type TEXT NOT NULL,
            service_date TEXT NOT NULL,
            notes TEXT,
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


def ensure_assessment_drafts_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS assessment_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            resident_id INTEGER,
            enrollment_id INTEGER,
            status TEXT NOT NULL DEFAULT 'draft',
            resident_name TEXT,
            assessment_type TEXT,
            form_payload TEXT NOT NULL,
            created_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS assessment_drafts (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            resident_id INTEGER REFERENCES residents(id),
            enrollment_id INTEGER REFERENCES program_enrollments(id),
            status TEXT NOT NULL DEFAULT 'draft',
            resident_name TEXT,
            assessment_type TEXT,
            form_payload TEXT NOT NULL,
            created_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_case_manager_updates_columns() -> None:
    statements = [
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS updated_grit INTEGER",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS parenting_class_completed INTEGER",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS warrants_or_fines_paid INTEGER",
    ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def ensure_intake_drafts_columns() -> None:
    statements = [
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS shelter TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft'",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS resident_name TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS entry_date TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS form_payload TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def ensure_assessment_drafts_columns() -> None:
    statements = [
        "ALTER TABLE assessment_drafts ADD COLUMN IF NOT EXISTS shelter TEXT",
        "ALTER TABLE assessment_drafts ADD COLUMN IF NOT EXISTS resident_id INTEGER",
        "ALTER TABLE assessment_drafts ADD COLUMN IF NOT EXISTS enrollment_id INTEGER",
        "ALTER TABLE assessment_drafts ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft'",
        "ALTER TABLE assessment_drafts ADD COLUMN IF NOT EXISTS resident_name TEXT",
        "ALTER TABLE assessment_drafts ADD COLUMN IF NOT EXISTS assessment_type TEXT",
        "ALTER TABLE assessment_drafts ADD COLUMN IF NOT EXISTS form_payload TEXT",
        "ALTER TABLE assessment_drafts ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER",
        "ALTER TABLE assessment_drafts ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE assessment_drafts ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


# ✅ NEW
def ensure_client_services_columns() -> None:
    statements = [
        "ALTER TABLE client_services ADD COLUMN IF NOT EXISTS case_manager_update_id INTEGER",
    ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


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
            CREATE INDEX IF NOT EXISTS client_services_enrollment_idx
            ON client_services (enrollment_id)
            """
        )
    except Exception:
        pass

    # ✅ NEW INDEX
    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS client_services_case_note_idx
            ON client_services (case_manager_update_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS client_services_service_type_idx
            ON client_services (service_type)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS client_services_service_date_idx
            ON client_services (service_date)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS client_services_enrollment_date_idx
            ON client_services (enrollment_id, service_date)
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

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS assessment_drafts_status_idx
            ON assessment_drafts (status)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS assessment_drafts_shelter_idx
            ON assessment_drafts (shelter)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS assessment_drafts_resident_idx
            ON assessment_drafts (resident_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS assessment_drafts_enrollment_idx
            ON assessment_drafts (enrollment_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS assessment_drafts_shelter_status_updated_idx
            ON assessment_drafts (shelter, status, updated_at)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS assessment_drafts_created_by_idx
            ON assessment_drafts (created_by_user_id)
            """
        )
    except Exception:
        pass


def ensure_tables(kind: str) -> None:
    ensure_case_manager_updates_table(kind)
    ensure_case_manager_calendar_events_table(kind)
    ensure_client_services_table(kind)
    ensure_intake_drafts_table(kind)
    ensure_assessment_drafts_table(kind)
    ensure_case_manager_updates_columns()
    ensure_intake_drafts_columns()
    ensure_assessment_drafts_columns()
    ensure_client_services_columns()  # ✅ NEW
    ensure_indexes()
