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
            setbacks_or_incidents TEXT,
            action_items TEXT,
            next_appointment TEXT,
            overall_summary TEXT,
            updated_grit INTEGER,
            parenting_class_completed INTEGER,
            warrants_or_fines_paid INTEGER,
            ready_for_next_level INTEGER,
            recommended_next_level TEXT,
            blocker_reason TEXT,
            override_or_exception TEXT,
            staff_review_note TEXT,
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
            setbacks_or_incidents TEXT,
            action_items TEXT,
            next_appointment TEXT,
            overall_summary TEXT,
            updated_grit INTEGER,
            parenting_class_completed INTEGER,
            warrants_or_fines_paid INTEGER,
            ready_for_next_level BOOLEAN,
            recommended_next_level TEXT,
            blocker_reason TEXT,
            override_or_exception TEXT,
            staff_review_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_case_manager_update_summary_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS case_manager_update_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_manager_update_id INTEGER NOT NULL,
            change_group TEXT NOT NULL,
            change_type TEXT,
            item_key TEXT,
            item_label TEXT,
            old_value TEXT,
            new_value TEXT,
            detail TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (case_manager_update_id) REFERENCES case_manager_updates(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS case_manager_update_summary (
            id SERIAL PRIMARY KEY,
            case_manager_update_id INTEGER NOT NULL REFERENCES case_manager_updates(id),
            change_group TEXT NOT NULL,
            change_type TEXT,
            item_key TEXT,
            item_label TEXT,
            old_value TEXT,
            new_value TEXT,
            detail TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
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


def ensure_case_manager_updates_columns() -> None:
    statements = [
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS next_appointment TEXT",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS overall_summary TEXT",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS updated_grit INTEGER",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS parenting_class_completed INTEGER",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS warrants_or_fines_paid INTEGER",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS setbacks_or_incidents TEXT",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS ready_for_next_level BOOLEAN",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS recommended_next_level TEXT",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS blocker_reason TEXT",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS override_or_exception TEXT",
        "ALTER TABLE case_manager_updates ADD COLUMN IF NOT EXISTS staff_review_note TEXT",
    ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def ensure_case_manager_update_summary_columns() -> None:
    statements = [
        "ALTER TABLE case_manager_update_summary ADD COLUMN IF NOT EXISTS change_type TEXT",
        "ALTER TABLE case_manager_update_summary ADD COLUMN IF NOT EXISTS item_key TEXT",
        "ALTER TABLE case_manager_update_summary ADD COLUMN IF NOT EXISTS item_label TEXT",
        "ALTER TABLE case_manager_update_summary ADD COLUMN IF NOT EXISTS old_value TEXT",
        "ALTER TABLE case_manager_update_summary ADD COLUMN IF NOT EXISTS new_value TEXT",
        "ALTER TABLE case_manager_update_summary ADD COLUMN IF NOT EXISTS detail TEXT",
        "ALTER TABLE case_manager_update_summary ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0",
        "ALTER TABLE case_manager_update_summary ADD COLUMN IF NOT EXISTS created_at TEXT",
    ]

    for statement in statements:
        try:
            db_execute(statement)
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


def ensure_case_notes_indexes() -> None:
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
            CREATE INDEX IF NOT EXISTS case_manager_update_summary_note_idx
            ON case_manager_update_summary (case_manager_update_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS case_manager_update_summary_group_idx
            ON case_manager_update_summary (change_group)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS case_manager_update_summary_note_group_idx
            ON case_manager_update_summary (case_manager_update_id, change_group, sort_order)
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


def ensure_tables(kind: str) -> None:
    ensure_case_manager_updates_table(kind)
    ensure_case_manager_update_summary_table(kind)
    ensure_client_services_table(kind)
    ensure_case_manager_updates_columns()
    ensure_case_manager_update_summary_columns()
    ensure_client_services_columns()
