"""
Resident identity and resident centered schema logic.
"""

from __future__ import annotations

import secrets

from core.db import db_execute, db_fetchall, db_fetchone

from .schema_helpers import create_table


def _make_resident_code(length: int = 8) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def ensure_residents_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS residents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            resident_code TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS residents (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            resident_code TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
    )


def ensure_sms_consent_columns(kind: str) -> None:
    if kind == "pg":
        try:
            db_execute(
                "ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in BOOLEAN NOT NULL DEFAULT FALSE"
            )
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in_source TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_out_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_out_source TEXT")
        except Exception:
            pass
    else:
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in_source TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_out_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_out_source TEXT")
        except Exception:
            pass


def ensure_resident_code_schema(kind: str) -> None:
    try:
        if kind == "pg":
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS resident_code TEXT")
        else:
            db_execute("ALTER TABLE residents ADD COLUMN resident_code TEXT")
    except Exception:
        pass

    try:
        db_execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS residents_resident_code_uq "
            "ON residents (resident_code)"
        )
    except Exception:
        pass


def ensure_indexes() -> None:
    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS residents_shelter_active_name_idx "
            "ON residents (shelter, is_active, last_name, first_name)"
        )
    except Exception:
        pass


def backfill_resident_codes(kind: str) -> None:
    rows = db_fetchall(
        "SELECT id FROM residents WHERE resident_code IS NULL OR resident_code = ''"
    )

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
    ensure_sms_consent_columns(kind)
    ensure_resident_code_schema(kind)
