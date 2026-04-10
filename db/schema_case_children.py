from __future__ import annotations

from core.db import db_execute

from .schema_helpers import create_table


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
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TEXT,
            deleted_by_staff_user_id INTEGER,
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
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TEXT,
            deleted_by_staff_user_id INTEGER,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )


def ensure_child_services_columns() -> None:
    statements = [
        "ALTER TABLE child_services ADD COLUMN IF NOT EXISTS quantity INTEGER",
        "ALTER TABLE child_services ADD COLUMN IF NOT EXISTS unit TEXT",
        "ALTER TABLE child_services ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE child_services ADD COLUMN IF NOT EXISTS deleted_at TEXT",
        "ALTER TABLE child_services ADD COLUMN IF NOT EXISTS deleted_by_staff_user_id INTEGER",
    ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass

    try:
        db_execute(
            """
            UPDATE child_services
            SET
                is_deleted = TRUE,
                deleted_at = COALESCE(deleted_at, updated_at)
            WHERE COALESCE(outcome, '') = 'deleted'
            """
        )
    except Exception:
        pass


def ensure_case_children_indexes() -> None:
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
            CREATE INDEX IF NOT EXISTS child_services_child_deleted_idx
            ON child_services (resident_child_id, is_deleted)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS child_services_enrollment_deleted_idx
            ON child_services (enrollment_id, is_deleted)
            """
        )
    except Exception:
        pass


def ensure_tables(kind: str) -> None:
    ensure_child_services_table(kind)
    ensure_child_services_columns()
