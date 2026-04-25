"""
Resident identity and resident centered schema logic.
"""

from __future__ import annotations

import contextlib
import secrets

from core.db import db_execute, db_fetchall, db_fetchone
from .schema_helpers import create_table, safe_add_column


def _make_resident_code(length: int = 8) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def ensure_residents_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS residents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))),
            resident_code TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            birth_year INTEGER,
            phone TEXT,
            email TEXT,
            emergency_contact_name TEXT,
            emergency_contact_relationship TEXT,
            emergency_contact_phone TEXT,
            program_level TEXT,
            level_start_date TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS residents (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL DEFAULT md5(random()::text || clock_timestamp()::text),
            resident_code TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            birth_year INTEGER,
            phone TEXT,
            email TEXT,
            emergency_contact_name TEXT,
            emergency_contact_relationship TEXT,
            emergency_contact_phone TEXT,
            program_level TEXT,
            level_start_date TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )


def ensure_resident_code_schema(kind: str) -> None:
    with contextlib.suppress(Exception):
        safe_add_column(kind, "residents", "resident_code TEXT")

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS residents_resident_code_uq ON residents (resident_code)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS residents_resident_identifier_uq ON residents (resident_identifier)"
        )


def backfill_resident_codes(kind: str) -> None:
    rows = db_fetchall("SELECT id FROM residents WHERE resident_code IS NULL OR resident_code = ''")

    for row in rows or []:
        resident_id = row["id"] if isinstance(row, dict) else row[0]
        code = _make_resident_code()

        for _ in range(10):
            exists = db_fetchone(
                "SELECT id FROM residents WHERE resident_code = %s"
                if kind == "pg"
                else "SELECT id FROM residents WHERE resident_code = ?",
                (code,),
            )
            if not exists:
                break
            code = _make_resident_code()

        db_execute(
            "UPDATE residents SET resident_code = %s WHERE id = %s"
            if kind == "pg"
            else "UPDATE residents SET resident_code = ? WHERE id = ?",
            (code, resident_id),
        )


def ensure_tables(kind: str) -> None:
    ensure_residents_table(kind)


def ensure_columns_and_constraints(kind: str) -> None:
    ensure_resident_code_schema(kind)
    backfill_resident_codes(kind)


def ensure_indexes() -> None:
    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS residents_shelter_active_name_idx ON residents (shelter, is_active, last_name, first_name)"
        )
