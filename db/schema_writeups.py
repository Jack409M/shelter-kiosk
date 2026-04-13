from __future__ import annotations

import contextlib

from core.db import db_execute

from .schema_helpers import create_table


def ensure_resident_writeups_table(kind: str) -> None:
    create_table(
        kind,
        # SQLite
        """
        CREATE TABLE IF NOT EXISTS resident_writeups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            shelter_snapshot TEXT NOT NULL,
            incident_date TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'Low',
            summary TEXT NOT NULL,
            full_notes TEXT,
            action_taken TEXT,
            status TEXT NOT NULL DEFAULT 'Open',
            resolution_notes TEXT,
            resolved_at TEXT,
            disciplinary_outcome TEXT,
            probation_start_date TEXT,
            probation_end_date TEXT,
            pre_termination_date TEXT,
            blocks_passes BOOLEAN NOT NULL DEFAULT FALSE,
            created_by_staff_user_id INTEGER,
            updated_by_staff_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id)
        )
        """,
        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS resident_writeups (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            shelter_snapshot TEXT NOT NULL,
            incident_date TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'Low',
            summary TEXT NOT NULL,
            full_notes TEXT,
            action_taken TEXT,
            status TEXT NOT NULL DEFAULT 'Open',
            resolution_notes TEXT,
            resolved_at TEXT,
            disciplinary_outcome TEXT,
            probation_start_date TEXT,
            probation_end_date TEXT,
            pre_termination_date TEXT,
            blocks_passes BOOLEAN NOT NULL DEFAULT FALSE,
            created_by_staff_user_id INTEGER,
            updated_by_staff_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_resident_writeups_columns() -> None:
    statements = [
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS shelter_snapshot TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS incident_date TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS category TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS severity TEXT DEFAULT 'Low'",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS summary TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS full_notes TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS action_taken TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Open'",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS resolution_notes TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS resolved_at TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS disciplinary_outcome TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS probation_start_date TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS probation_end_date TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS pre_termination_date TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS blocks_passes BOOLEAN DEFAULT FALSE",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS created_by_staff_user_id INTEGER",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS updated_by_staff_user_id INTEGER",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE resident_writeups ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def ensure_writeups_indexes() -> None:
    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_writeups_resident_idx
            ON resident_writeups (resident_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_writeups_incident_date_idx
            ON resident_writeups (incident_date)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_writeups_resident_incident_date_idx
            ON resident_writeups (resident_id, incident_date)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_writeups_status_idx
            ON resident_writeups (status)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_writeups_outcome_idx
            ON resident_writeups (disciplinary_outcome)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_writeups_blocks_passes_idx
            ON resident_writeups (resident_id, blocks_passes, status)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_writeups_probation_window_idx
            ON resident_writeups (resident_id, probation_start_date, probation_end_date)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_writeups_pre_term_date_idx
            ON resident_writeups (resident_id, pre_termination_date)
            """
        )


def ensure_tables(kind: str) -> None:
    ensure_resident_writeups_table(kind)
    ensure_resident_writeups_columns()
