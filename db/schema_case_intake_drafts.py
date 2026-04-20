from __future__ import annotations

import contextlib

from core.db import db_execute

from .schema_helpers import create_table


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
        """,
    )


def ensure_intake_drafts_columns(kind: str) -> None:
    statements = [
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS resident_id INTEGER",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS enrollment_id INTEGER",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS shelter TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft'",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS resident_name TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS entry_date TEXT",
        (
            "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS draft_data JSONB "
            "DEFAULT '{}'::jsonb"
            if kind == "pg"
            else "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS draft_data TEXT"
        ),
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS form_payload TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE intake_drafts ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)

    if kind == "pg":
        with contextlib.suppress(Exception):
            db_execute(
                """
                UPDATE intake_drafts
                SET draft_data = '{}'::jsonb
                WHERE draft_data IS NULL
                """
            )
        return

    with contextlib.suppress(Exception):
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

    with contextlib.suppress(Exception):
        db_execute(
            """
            UPDATE intake_drafts
            SET draft_data = '{}'
            WHERE draft_data IS NULL OR draft_data = ''
            """
        )


def ensure_case_intake_drafts_indexes() -> None:
    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_status_idx
            ON intake_drafts (status)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_shelter_idx
            ON intake_drafts (shelter)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_entry_date_idx
            ON intake_drafts (entry_date)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_resident_idx
            ON intake_drafts (resident_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_enrollment_idx
            ON intake_drafts (enrollment_id)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_shelter_status_updated_idx
            ON intake_drafts (shelter, status, updated_at)
            """
        )

    with contextlib.suppress(Exception):
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_drafts_created_by_idx
            ON intake_drafts (created_by_user_id)
            """
        )


def ensure_tables(kind: str) -> None:
    ensure_intake_drafts_table(kind)
    ensure_intake_drafts_columns(kind)
