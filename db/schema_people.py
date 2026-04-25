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
            gender TEXT,
            race TEXT,
            ethnicity TEXT,
            program_level TEXT,
            level_start_date TEXT,
            step_changed_at TEXT,
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
            gender TEXT,
            race TEXT,
            ethnicity TEXT,
            program_level TEXT,
            level_start_date TEXT,
            step_changed_at TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )


def ensure_resident_profile_columns(kind: str) -> None:
    columns = [
        "resident_code TEXT",
        "birth_year INTEGER",
        "phone TEXT",
        "email TEXT",
        "emergency_contact_name TEXT",
        "emergency_contact_relationship TEXT",
        "emergency_contact_phone TEXT",
        "gender TEXT",
        "race TEXT",
        "ethnicity TEXT",
        "program_level TEXT",
        "level_start_date TEXT",
        "step_changed_at TEXT",
    ]

    for column_sql in columns:
        with contextlib.suppress(Exception):
            safe_add_column(kind, "residents", column_sql)


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


def ensure_resident_children_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_children (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            child_name TEXT,
            birth_year INTEGER,
            relationship TEXT,
            living_status TEXT,
            receives_survivor_benefit INTEGER NOT NULL DEFAULT 0,
            survivor_benefit_amount REAL,
            survivor_benefit_notes TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (resident_id) REFERENCES residents(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_children (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            child_name TEXT,
            birth_year INTEGER,
            relationship TEXT,
            living_status TEXT,
            receives_survivor_benefit BOOLEAN NOT NULL DEFAULT FALSE,
            survivor_benefit_amount DOUBLE PRECISION,
            survivor_benefit_notes TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """,
    )


def ensure_resident_child_income_supports_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_child_income_supports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER,
            resident_id INTEGER,
            enrollment_id INTEGER,
            support_type TEXT,
            monthly_amount REAL,
            amount REAL,
            notes TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (child_id) REFERENCES resident_children(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_child_income_supports (
            id SERIAL PRIMARY KEY,
            child_id INTEGER REFERENCES resident_children(id),
            resident_id INTEGER,
            enrollment_id INTEGER,
            support_type TEXT,
            monthly_amount DOUBLE PRECISION,
            amount DOUBLE PRECISION,
            notes TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT,
            updated_at TEXT
        )
        """,
    )


def ensure_child_income_support_columns(kind: str) -> None:
    columns = [
        "child_id INTEGER",
        "resident_id INTEGER",
        "enrollment_id INTEGER",
        "support_type TEXT",
        "monthly_amount DOUBLE PRECISION" if kind == "pg" else "monthly_amount REAL",
        "amount DOUBLE PRECISION" if kind == "pg" else "amount REAL",
        "notes TEXT",
        "is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "created_at TEXT",
        "updated_at TEXT",
    ]

    for column_sql in columns:
        with contextlib.suppress(Exception):
            safe_add_column(kind, "resident_child_income_supports", column_sql)


def ensure_tables(kind: str) -> None:
    ensure_residents_table(kind)
    ensure_resident_children_table(kind)
    ensure_resident_child_income_supports_table(kind)


def ensure_columns_and_constraints(kind: str) -> None:
    ensure_resident_profile_columns(kind)
    ensure_resident_code_schema(kind)
    ensure_child_income_support_columns(kind)
    backfill_resident_codes(kind)


def ensure_indexes() -> None:
    index_statements = [
        "CREATE INDEX IF NOT EXISTS residents_shelter_active_name_idx ON residents (shelter, is_active, last_name, first_name)",
        "CREATE INDEX IF NOT EXISTS resident_children_resident_idx ON resident_children (resident_id)",
        "CREATE INDEX IF NOT EXISTS resident_child_income_supports_child_idx ON resident_child_income_supports (child_id)",
        "CREATE INDEX IF NOT EXISTS resident_child_income_supports_resident_idx ON resident_child_income_supports (resident_id)",
    ]
    for statement in index_statements:
        with contextlib.suppress(Exception):
            db_execute(statement)
