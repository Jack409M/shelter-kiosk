"""
Case management schema.

Tracks structured case manager interactions with residents
during program participation.

Locked intake rule for this project:

There is one official intake baseline.
Drafts may be saved and resumed any number of times,
but draft data is not reportable and does not become official
until final submit.

This schema keeps intake drafts in a single draft table.
assessment_drafts is no longer owned here.

Important transition note:
draft_data is the new canonical JSON payload column.
form_payload is kept temporarily as a legacy compatibility bridge
until route code is fully migrated.
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
            quantity INTEGER,
            unit TEXT,
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
            quantity INTEGER,
            unit TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_child_services_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS child_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_child_id INTEGER NOT NULL,
            enrollment_id INTEGER NOT NULL,
            service_date TEXT,
            service_type TEXT,
            outcome TEXT,
            quantity INTEGER,
            unit TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (resident_child_id) REFERENCES resident_children(id),
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS child_services (
            id SERIAL PRIMARY KEY,
            resident_child_id INTEGER NOT NULL REFERENCES resident_children(id),
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            service_date TEXT,
            service_type TEXT,
            outcome TEXT,
            quantity INTEGER,
            unit TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
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
            resident_id INTEGER,
            enrollment_id INTEGER,
            shelter TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            resident_name TEXT,
            entry_date TEXT,
            draft_data TEXT NOT NULL DEFAULT '{}',
            form_payload TEXT,
            created_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS intake_drafts (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER REFERENCES residents(id),
            enrollment_id INTEGER REFERENCES program_enrollments(id),
            shelter TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            resident_name TEXT,
            entry_date TEXT,
            draft_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            form_payload TEXT,
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
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS resident_id INTEGER",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS enrollment_id INTEGER",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS shelter TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft'",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS resident_name TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS entry_date TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS draft_data TEXT",
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

    # Backfill canonical draft_data from legacy form_payload when possible.
    try:
        db_execute(
            """
            UPDATE intake_drafts
            SET draft_data = form_payload
            WHERE
                (draft_data IS NULL OR draft_data = '')
                AND form_payload IS NOT NULL
                AND form_payload <> ''
            """
        )
    except Exception:
        pass

    # Ensure draft_data is never left empty after migration runs.
    try:
        db_execute(
            """
            UPDATE intake_drafts
            SET draft_data = '{}'
            WHERE draft_data IS NULL OR draft_data = ''
            """
        )
    except Exception:
        pass


def ensure_client_services_columns() -> None:
    statements = [
        "ALTER TABLE client_services ADD COLUMN IF NOT EXISTS case_manager_update_id INTEGER",
        "ALTER TABLE client_services ADD COLUMN IF NOT EXISTS quantity INTEGER",
        "ALTER TABLE client_services ADD COLUMN IF NOT EXISTS unit TEXT",
    ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def ensure_child_services_columns() -> None:
    statements = [
        "ALTER TABLE child_services ADD COLUMN IF NOT EXISTS quantity INTEGER",
        "ALTER TABLE child_services ADD COLUMN IF NOT EXISTS unit TEXT",
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
            CREATE INDEX IF NOT EXISTS child_services_child_idx
            ON child_services (resident_child_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS child_services_enrollment_idx
            ON child_services (enrollment_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS child_services_service_type_idx
            ON child_services (service_type)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS child_services_service_date_idx
            ON child_services (service_date)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS child_services_child_enrollment_idx
            ON child_services (resident_child_id, enrollment_id)
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
            CREATE INDEX IF NOT EXISTS intake_drafts_resident_idx
            ON intake_drafts (resident_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_enrollment_idx
            ON intake_drafts (enrollment_id)
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
    ensure_client_services_table(kind)
    ensure_child_services_table(kind)
    ensure_intake_drafts_table(kind)
    ensure_case_manager_updates_columns()
    ensure_intake_drafts_columns()
    ensure_client_services_columns()
    ensure_child_services_columns()
    ensure_indexes()
