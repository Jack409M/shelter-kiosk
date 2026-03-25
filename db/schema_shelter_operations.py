from __future__ import annotations

from core.db import db_execute

from .schema_helpers import create_table


def ensure_chore_tables(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS chore_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS chore_templates (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )

    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS chore_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            chore_id INTEGER NOT NULL,
            assigned_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'assigned',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (chore_id) REFERENCES chore_templates(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS chore_assignments (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            chore_id INTEGER NOT NULL REFERENCES chore_templates(id),
            assigned_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'assigned',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_indexes() -> None:
    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_templates_shelter_idx
            ON chore_templates (shelter)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_templates_active_idx
            ON chore_templates (active)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_templates_shelter_active_sort_idx
            ON chore_templates (shelter, active, sort_order)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_assignments_resident_idx
            ON chore_assignments (resident_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_assignments_chore_idx
            ON chore_assignments (chore_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_assignments_assigned_date_idx
            ON chore_assignments (assigned_date)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_assignments_status_idx
            ON chore_assignments (status)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_assignments_resident_date_idx
            ON chore_assignments (resident_id, assigned_date)
            """
        )
    except Exception:
        pass


def ensure_tables(kind: str) -> None:
    ensure_chore_tables(kind)
