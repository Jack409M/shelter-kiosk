"""
Resident identity and resident centered schema logic.
"""

from __future__ import annotations

import secrets

from core.db import db_execute, db_fetchall, db_fetchone

from .schema_helpers import create_table


def _make_resident_code(length: int = 8) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def _sqlite_column_exists(table_name: str, column_name: str) -> bool:
    try:
        rows = db_fetchall(f"PRAGMA table_info({table_name})")
    except Exception:
        return False

    for row in rows or []:
        name = row["name"] if isinstance(row, dict) else row[1]
        if str(name).strip().lower() == column_name.strip().lower():
            return True
    return False


def _pg_column_exists(table_name: str, column_name: str) -> bool:
    row = db_fetchone(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return bool(row)


def column_exists(kind: str, table_name: str, column_name: str) -> bool:
    if kind == "pg":
        return _pg_column_exists(table_name, column_name)
    return _sqlite_column_exists(table_name, column_name)


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
            birth_year INTEGER,
            phone TEXT,
            email TEXT,
            emergency_contact_name TEXT,
            emergency_contact_relationship TEXT,
            emergency_contact_phone TEXT,
            medical_alerts TEXT,
            medical_notes TEXT,
            program_level TEXT,
            sponsor_name TEXT,
            employer_name TEXT,
            monthly_income REAL,
            step_current INTEGER,
            step_changed_at TEXT,
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
            birth_year INTEGER,
            phone TEXT,
            email TEXT,
            emergency_contact_name TEXT,
            emergency_contact_relationship TEXT,
            emergency_contact_phone TEXT,
            medical_alerts TEXT,
            medical_notes TEXT,
            program_level TEXT,
            sponsor_name TEXT,
            employer_name TEXT,
            monthly_income DOUBLE PRECISION,
            step_current INTEGER,
            step_changed_at TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
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
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """,
    )


def ensure_resident_substances_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_substances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            substance TEXT,
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (resident_id) REFERENCES residents(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_substances (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            substance TEXT,
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TEXT,
            updated_at TEXT
        )
        """,
    )


def ensure_basic_profile_columns(kind: str) -> None:
    if kind == "pg":
        statements = [
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS birth_year INTEGER",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS email TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS emergency_contact_name TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS emergency_contact_relationship TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS emergency_contact_phone TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS medical_alerts TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS medical_notes TEXT",
        ]
    else:
        statements = [
            "ALTER TABLE residents ADD COLUMN birth_year INTEGER",
            "ALTER TABLE residents ADD COLUMN email TEXT",
            "ALTER TABLE residents ADD COLUMN emergency_contact_name TEXT",
            "ALTER TABLE residents ADD COLUMN emergency_contact_relationship TEXT",
            "ALTER TABLE residents ADD COLUMN emergency_contact_phone TEXT",
            "ALTER TABLE residents ADD COLUMN medical_alerts TEXT",
            "ALTER TABLE residents ADD COLUMN medical_notes TEXT",
        ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def ensure_recovery_profile_columns(kind: str) -> None:
    if kind == "pg":
        statements = [
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS program_level TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS sponsor_name TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS employer_name TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS monthly_income DOUBLE PRECISION",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS step_current INTEGER",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS step_changed_at TEXT",
        ]
    else:
        statements = [
            "ALTER TABLE residents ADD COLUMN program_level TEXT",
            "ALTER TABLE residents ADD COLUMN sponsor_name TEXT",
            "ALTER TABLE residents ADD COLUMN employer_name TEXT",
            "ALTER TABLE residents ADD COLUMN monthly_income REAL",
            "ALTER TABLE residents ADD COLUMN step_current INTEGER",
            "ALTER TABLE residents ADD COLUMN step_changed_at TEXT",
        ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass

    try:
        db_execute(
            """
            UPDATE residents
            SET step_current = aa_step_current
            WHERE step_current IS NULL
              AND aa_step_current IS NOT NULL
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            UPDATE residents
            SET step_changed_at = aa_step_changed_at
            WHERE (step_changed_at IS NULL OR step_changed_at = '')
              AND aa_step_changed_at IS NOT NULL
              AND aa_step_changed_at <> ''
            """
        )
    except Exception:
        pass


def ensure_reporting_columns(kind: str) -> None:
    if kind == "pg":
        statements = [
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS gender TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS race TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS ethnicity TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS veteran BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS disability BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS marital_status TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS city TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS last_zipcode_of_residence TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS place_staying_before_entry TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS length_of_time_in_amarillo_upon_entry TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS date_entered TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS date_exit_dwc TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS graduate_dwc BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS reason_for_exit TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS leave_ama_upon_exit BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS status TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS updated_at TEXT",
        ]
    else:
        statements = [
            "ALTER TABLE residents ADD COLUMN gender TEXT",
            "ALTER TABLE residents ADD COLUMN race TEXT",
            "ALTER TABLE residents ADD COLUMN ethnicity TEXT",
            "ALTER TABLE residents ADD COLUMN veteran INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE residents ADD COLUMN disability INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE residents ADD COLUMN marital_status TEXT",
            "ALTER TABLE residents ADD COLUMN city TEXT",
            "ALTER TABLE residents ADD COLUMN last_zipcode_of_residence TEXT",
            "ALTER TABLE residents ADD COLUMN place_staying_before_entry TEXT",
            "ALTER TABLE residents ADD COLUMN length_of_time_in_amarillo_upon_entry TEXT",
            "ALTER TABLE residents ADD COLUMN date_entered TEXT",
            "ALTER TABLE residents ADD COLUMN date_exit_dwc TEXT",
            "ALTER TABLE residents ADD COLUMN graduate_dwc INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE residents ADD COLUMN reason_for_exit TEXT",
            "ALTER TABLE residents ADD COLUMN leave_ama_upon_exit INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE residents ADD COLUMN status TEXT",
            "ALTER TABLE residents ADD COLUMN updated_at TEXT",
        ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


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


def backfill_birth_year_from_legacy_dob(kind: str) -> None:
    if not column_exists(kind, "residents", "dob"):
        return

    if not column_exists(kind, "residents", "birth_year"):
        return

    rows = db_fetchall(
        "SELECT id, dob, birth_year FROM residents "
        "WHERE dob IS NOT NULL AND dob <> '' "
        "AND birth_year IS NULL"
    )

    for row in rows or []:
        if isinstance(row, dict):
            resident_id = row["id"]
            dob_value = row["dob"]
        else:
            resident_id = row[0]
            dob_value = row[1]

        dob_text = str(dob_value or "").strip()
        if len(dob_text) < 4:
            continue

        year_text = dob_text[:4]
        if not year_text.isdigit():
            continue

        birth_year = int(year_text)

        db_execute(
            "UPDATE residents SET birth_year = %s WHERE id = %s"
            if kind == "pg"
            else "UPDATE residents SET birth_year = ? WHERE id = ?",
            (birth_year, resident_id),
        )


def ensure_indexes() -> None:
    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS residents_shelter_active_name_idx "
            "ON residents (shelter, is_active, last_name, first_name)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS residents_resident_identifier_idx "
            "ON residents (resident_identifier)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS residents_status_idx "
            "ON residents (status)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS residents_date_entered_idx "
            "ON residents (date_entered)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS residents_date_exit_dwc_idx "
            "ON residents (date_exit_dwc)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS residents_birth_year_idx "
            "ON residents (birth_year)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS residents_program_level_idx "
            "ON residents (program_level)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS residents_step_current_idx "
            "ON residents (step_current)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_children_resident_idx "
            "ON resident_children (resident_id)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_children_living_status_idx "
            "ON resident_children (living_status)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_substances_resident_idx "
            "ON resident_substances (resident_id)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_substances_primary_idx "
            "ON resident_substances (is_primary)"
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
    ensure_resident_children_table(kind)
    ensure_resident_substances_table(kind)


def ensure_columns_and_constraints(kind: str) -> None:
    ensure_basic_profile_columns(kind)
    ensure_recovery_profile_columns(kind)
    ensure_reporting_columns(kind)
    ensure_sms_consent_columns(kind)
    ensure_resident_code_schema(kind)
    backfill_birth_year_from_legacy_dob(kind)
    backfill_resident_codes(kind)
