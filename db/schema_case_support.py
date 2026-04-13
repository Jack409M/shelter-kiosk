from __future__ import annotations

import contextlib

from core.db import db_execute

from .schema_helpers import create_table


def ensure_resident_needs_table(kind: str) -> None:
    create_table(
        kind,
        # SQLite
        """
        CREATE TABLE IF NOT EXISTS resident_needs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            need_key TEXT NOT NULL,
            need_label TEXT NOT NULL,
            source_field TEXT,
            source_value TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            resolution_note TEXT,
            resolved_at TEXT,
            resolved_by_staff_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id),
            UNIQUE (enrollment_id, need_key)
        )
        """,
        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS resident_needs (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            need_key TEXT NOT NULL,
            need_label TEXT NOT NULL,
            source_field TEXT,
            source_value TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            resolution_note TEXT,
            resolved_at TEXT,
            resolved_by_staff_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (enrollment_id, need_key)
        )
        """,
    )


def ensure_resident_medications_table(kind: str) -> None:
    create_table(
        kind,
        # SQLite
        """
        CREATE TABLE IF NOT EXISTS resident_medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            enrollment_id INTEGER,
            medication_name TEXT NOT NULL,
            dosage TEXT,
            frequency TEXT,
            purpose TEXT,
            prescribed_by TEXT,
            started_on TEXT,
            ended_on TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            notes TEXT,
            created_by_staff_user_id INTEGER,
            updated_by_staff_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,
        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS resident_medications (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            enrollment_id INTEGER REFERENCES program_enrollments(id),
            medication_name TEXT NOT NULL,
            dosage TEXT,
            frequency TEXT,
            purpose TEXT,
            prescribed_by TEXT,
            started_on TEXT,
            ended_on TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            notes TEXT,
            created_by_staff_user_id INTEGER,
            updated_by_staff_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_resident_ua_log_table(kind: str) -> None:
    create_table(
        kind,
        # SQLite
        """
        CREATE TABLE IF NOT EXISTS resident_ua_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            enrollment_id INTEGER,
            ua_date TEXT NOT NULL,
            result TEXT,
            substances_detected TEXT,
            administered_by_staff_user_id INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,
        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS resident_ua_log (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            enrollment_id INTEGER REFERENCES program_enrollments(id),
            ua_date TEXT NOT NULL,
            result TEXT,
            substances_detected TEXT,
            administered_by_staff_user_id INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_resident_living_area_inspections_table(kind: str) -> None:
    create_table(
        kind,
        # SQLite
        """
        CREATE TABLE IF NOT EXISTS resident_living_area_inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            enrollment_id INTEGER,
            inspection_date TEXT NOT NULL,
            passed BOOLEAN NOT NULL DEFAULT FALSE,
            inspected_by_staff_user_id INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,
        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS resident_living_area_inspections (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            enrollment_id INTEGER REFERENCES program_enrollments(id),
            inspection_date TEXT NOT NULL,
            passed BOOLEAN NOT NULL DEFAULT FALSE,
            inspected_by_staff_user_id INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_resident_budget_sessions_table(kind: str) -> None:
    create_table(
        kind,
        # SQLite
        """
        CREATE TABLE IF NOT EXISTS resident_budget_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            enrollment_id INTEGER,
            session_date TEXT NOT NULL,
            staff_user_id INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,
        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS resident_budget_sessions (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            enrollment_id INTEGER REFERENCES program_enrollments(id),
            session_date TEXT NOT NULL,
            staff_user_id INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_resident_needs_columns() -> None:
    statements = [
        "ALTER TABLE resident_needs ADD COLUMN IF NOT EXISTS source_field TEXT",
        "ALTER TABLE resident_needs ADD COLUMN IF NOT EXISTS source_value TEXT",
        "ALTER TABLE resident_needs ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'open'",
        "ALTER TABLE resident_needs ADD COLUMN IF NOT EXISTS resolution_note TEXT",
        "ALTER TABLE resident_needs ADD COLUMN IF NOT EXISTS resolved_at TEXT",
        "ALTER TABLE resident_needs ADD COLUMN IF NOT EXISTS resolved_by_staff_user_id INTEGER",
        "ALTER TABLE resident_needs ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE resident_needs ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def ensure_resident_medications_columns() -> None:
    statements = [
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS enrollment_id INTEGER",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS dosage TEXT",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS frequency TEXT",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS purpose TEXT",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS prescribed_by TEXT",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS started_on TEXT",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS ended_on TEXT",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS created_by_staff_user_id INTEGER",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS updated_by_staff_user_id INTEGER",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE resident_medications ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def ensure_resident_ua_log_columns() -> None:
    statements = [
        "ALTER TABLE resident_ua_log ADD COLUMN IF NOT EXISTS enrollment_id INTEGER",
        "ALTER TABLE resident_ua_log ADD COLUMN IF NOT EXISTS result TEXT",
        "ALTER TABLE resident_ua_log ADD COLUMN IF NOT EXISTS substances_detected TEXT",
        "ALTER TABLE resident_ua_log ADD COLUMN IF NOT EXISTS administered_by_staff_user_id INTEGER",
        "ALTER TABLE resident_ua_log ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE resident_ua_log ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE resident_ua_log ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def ensure_resident_living_area_inspections_columns() -> None:
    statements = [
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS enrollment_id INTEGER",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS passed BOOLEAN DEFAULT FALSE",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS inspected_by_staff_user_id INTEGER",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def ensure_resident_budget_sessions_columns() -> None:
    statements = [
        "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS enrollment_id INTEGER",
        "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS staff_user_id INTEGER",
        "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def ensure_case_support_indexes() -> None:
    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_needs_enrollment_idx
            ON resident_needs (enrollment_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_needs_status_idx
            ON resident_needs (status)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_needs_enrollment_status_idx
            ON resident_needs (enrollment_id, status)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS resident_needs_enrollment_key_uidx
            ON resident_needs (enrollment_id, need_key)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_medications_resident_idx
            ON resident_medications (resident_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_medications_enrollment_idx
            ON resident_medications (enrollment_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_medications_active_idx
            ON resident_medications (resident_id, is_active)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_ua_log_resident_idx
            ON resident_ua_log (resident_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_ua_log_enrollment_idx
            ON resident_ua_log (enrollment_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_ua_log_date_idx
            ON resident_ua_log (ua_date)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_ua_log_resident_date_idx
            ON resident_ua_log (resident_id, ua_date)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_living_area_inspections_resident_idx
            ON resident_living_area_inspections (resident_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_living_area_inspections_enrollment_idx
            ON resident_living_area_inspections (enrollment_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_living_area_inspections_date_idx
            ON resident_living_area_inspections (inspection_date)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_living_area_inspections_resident_date_idx
            ON resident_living_area_inspections (resident_id, inspection_date)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_budget_sessions_resident_idx
            ON resident_budget_sessions (resident_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_budget_sessions_enrollment_idx
            ON resident_budget_sessions (enrollment_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_budget_sessions_date_idx
            ON resident_budget_sessions (session_date)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_budget_sessions_resident_date_idx
            ON resident_budget_sessions (resident_id, session_date)
            """
        )


def ensure_tables(kind: str) -> None:
    ensure_resident_needs_table(kind)
    ensure_resident_medications_table(kind)
    ensure_resident_ua_log_table(kind)
    ensure_resident_living_area_inspections_table(kind)
    ensure_resident_budget_sessions_table(kind)
    ensure_resident_needs_columns()
    ensure_resident_medications_columns()
    ensure_resident_ua_log_columns()
    ensure_resident_living_area_inspections_columns()
    ensure_resident_budget_sessions_columns()
