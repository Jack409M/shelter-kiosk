"""
Resident identity and resident centered schema logic.
"""

from __future__ import annotations

import secrets

from flask import flash, redirect, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import parse_iso_date
from routes.case_management_parts.helpers import parse_money
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.helpers import yes_no_to_int

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
            level_start_date TEXT,
            sponsor_name TEXT,
            sponsor_active INTEGER,
            sobriety_date TEXT,
            drug_of_choice TEXT,
            treatment_graduation_date TEXT,
            employer_name TEXT,
            employment_status_current TEXT,
            employment_type_current TEXT,
            supervisor_name TEXT,
            supervisor_phone TEXT,
            unemployment_reason TEXT,
            employment_notes TEXT,
            monthly_income REAL,
            current_job_start_date TEXT,
            continuous_employment_start_date TEXT,
            previous_job_end_date TEXT,
            upward_job_change INTEGER,
            job_change_notes TEXT,
            employment_updated_at TEXT,
            step_current INTEGER,
            step_work_active INTEGER,
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
            level_start_date TEXT,
            sponsor_name TEXT,
            sponsor_active BOOLEAN,
            sobriety_date TEXT,
            drug_of_choice TEXT,
            treatment_graduation_date TEXT,
            employer_name TEXT,
            employment_status_current TEXT,
            employment_type_current TEXT,
            supervisor_name TEXT,
            supervisor_phone TEXT,
            unemployment_reason TEXT,
            employment_notes TEXT,
            monthly_income DOUBLE PRECISION,
            current_job_start_date TEXT,
            continuous_employment_start_date TEXT,
            previous_job_end_date TEXT,
            upward_job_change BOOLEAN,
            job_change_notes TEXT,
            employment_updated_at TEXT,
            step_current INTEGER,
            step_work_active BOOLEAN,
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
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS level_start_date TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS sponsor_name TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS sponsor_active BOOLEAN",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS sobriety_date TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS drug_of_choice TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS treatment_graduation_date TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS employer_name TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS employment_status_current TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS employment_type_current TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS supervisor_name TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS supervisor_phone TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS unemployment_reason TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS employment_notes TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS monthly_income DOUBLE PRECISION",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS current_job_start_date TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS continuous_employment_start_date TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS previous_job_end_date TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS upward_job_change BOOLEAN",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS job_change_notes TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS employment_updated_at TEXT",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS step_current INTEGER",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS step_work_active BOOLEAN",
            "ALTER TABLE residents ADD COLUMN IF NOT EXISTS step_changed_at TEXT",
        ]
    else:
        statements = [
            "ALTER TABLE residents ADD COLUMN program_level TEXT",
            "ALTER TABLE residents ADD COLUMN level_start_date TEXT",
            "ALTER TABLE residents ADD COLUMN sponsor_name TEXT",
            "ALTER TABLE residents ADD COLUMN sponsor_active INTEGER",
            "ALTER TABLE residents ADD COLUMN sobriety_date TEXT",
            "ALTER TABLE residents ADD COLUMN drug_of_choice TEXT",
            "ALTER TABLE residents ADD COLUMN treatment_graduation_date TEXT",
            "ALTER TABLE residents ADD COLUMN employer_name TEXT",
            "ALTER TABLE residents ADD COLUMN employment_status_current TEXT",
            "ALTER TABLE residents ADD COLUMN employment_type_current TEXT",
            "ALTER TABLE residents ADD COLUMN supervisor_name TEXT",
            "ALTER TABLE residents ADD COLUMN supervisor_phone TEXT",
            "ALTER TABLE residents ADD COLUMN unemployment_reason TEXT",
            "ALTER TABLE residents ADD COLUMN employment_notes TEXT",
            "ALTER TABLE residents ADD COLUMN monthly_income REAL",
            "ALTER TABLE residents ADD COLUMN current_job_start_date TEXT",
            "ALTER TABLE residents ADD COLUMN continuous_employment_start_date TEXT",
            "ALTER TABLE residents ADD COLUMN previous_job_end_date TEXT",
            "ALTER TABLE residents ADD COLUMN upward_job_change INTEGER",
            "ALTER TABLE residents ADD COLUMN job_change_notes TEXT",
            "ALTER TABLE residents ADD COLUMN employment_updated_at TEXT",
            "ALTER TABLE residents ADD COLUMN step_current INTEGER",
            "ALTER TABLE residents ADD COLUMN step_work_active INTEGER",
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

    try:
        db_execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS residents_resident_identifier_uq "
            "ON residents (resident_identifier)"
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
    index_statements = [
        "CREATE INDEX IF NOT EXISTS residents_shelter_active_name_idx ON residents (shelter, is_active, last_name, first_name)",
        "CREATE INDEX IF NOT EXISTS residents_resident_identifier_idx ON residents (resident_identifier)",
        "CREATE INDEX IF NOT EXISTS residents_status_idx ON residents (status)",
        "CREATE INDEX IF NOT EXISTS residents_date_entered_idx ON residents (date_entered)",
        "CREATE INDEX IF NOT EXISTS residents_date_exit_dwc_idx ON residents (date_exit_dwc)",
        "CREATE INDEX IF NOT EXISTS residents_birth_year_idx ON residents (birth_year)",
        "CREATE INDEX IF NOT EXISTS residents_program_level_idx ON residents (program_level)",
        "CREATE INDEX IF NOT EXISTS residents_step_current_idx ON residents (step_current)",
        "CREATE INDEX IF NOT EXISTS residents_current_job_start_date_idx ON residents (current_job_start_date)",
        "CREATE INDEX IF NOT EXISTS residents_continuous_employment_start_date_idx ON residents (continuous_employment_start_date)",
        "CREATE INDEX IF NOT EXISTS resident_children_resident_idx ON resident_children (resident_id)",
        "CREATE INDEX IF NOT EXISTS resident_children_resident_active_idx ON resident_children (resident_id, is_active)",
        "CREATE INDEX IF NOT EXISTS resident_children_living_status_idx ON resident_children (living_status)",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS resident_children_active_dedupe_uidx
        ON resident_children (
            resident_id,
            LOWER(COALESCE(child_name, '')),
            COALESCE(birth_year, -1),
            is_active
        )
        """,
        "CREATE INDEX IF NOT EXISTS resident_substances_resident_idx ON resident_substances (resident_id)",
        "CREATE INDEX IF NOT EXISTS resident_substances_primary_idx ON resident_substances (is_primary)",
    ]
    for statement in index_statements:
        try:
            db_execute(statement)
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


def update_recovery_profile_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            id,
            shelter,
            first_name,
            last_name
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        LIMIT 1
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    program_level = clean(request.form.get("program_level"))
    level_start_date = parse_iso_date(request.form.get("level_start_date"))
    step_current = parse_int(request.form.get("step_current"))
    sponsor_name = clean(request.form.get("sponsor_name"))
    sponsor_active = yes_no_to_int(request.form.get("sponsor_active"))
    step_work_active = yes_no_to_int(request.form.get("step_work_active"))
    sobriety_date = parse_iso_date(request.form.get("sobriety_date"))
    treatment_graduation_date = parse_iso_date(request.form.get("treatment_graduation_date"))
    drug_of_choice = clean(request.form.get("drug_of_choice"))
    employment_notes = clean(request.form.get("employment_notes"))

    employment_status_current = clean(request.form.get("employment_status_current"))
    employer_name = clean(request.form.get("employer_name"))
    employment_type_current = clean(request.form.get("employment_type_current"))
    monthly_income = parse_money(request.form.get("monthly_income"))
    current_job_start_date = parse_iso_date(request.form.get("current_job_start_date"))
    continuous_employment_start_date = parse_iso_date(
        request.form.get("continuous_employment_start_date")
    )
    previous_job_end_date = parse_iso_date(request.form.get("previous_job_end_date"))
    upward_job_change = yes_no_to_int(request.form.get("upward_job_change"))
    supervisor_name = clean(request.form.get("supervisor_name"))
    supervisor_phone = clean(request.form.get("supervisor_phone"))
    unemployment_reason = clean(request.form.get("unemployment_reason"))
    job_change_notes = clean(request.form.get("job_change_notes"))

    now = utcnow_iso()

    try:
        db_execute(
            f"""
            UPDATE residents
            SET
                program_level = {ph},
                level_start_date = {ph},
                step_current = {ph},
                sponsor_name = {ph},
                sponsor_active = {ph},
                step_work_active = {ph},
                sobriety_date = {ph},
                treatment_graduation_date = {ph},
                drug_of_choice = {ph},
                employment_notes = {ph},
                employment_status_current = {ph},
                employer_name = {ph},
                employment_type_current = {ph},
                monthly_income = {ph},
                current_job_start_date = {ph},
                continuous_employment_start_date = {ph},
                previous_job_end_date = {ph},
                upward_job_change = {ph},
                supervisor_name = {ph},
                supervisor_phone = {ph},
                unemployment_reason = {ph},
                job_change_notes = {ph},
                employment_updated_at = {ph},
                step_changed_at = {ph}
            WHERE id = {ph}
            """,
            (
                program_level,
                level_start_date.isoformat() if level_start_date else None,
                step_current,
                sponsor_name,
                sponsor_active,
                step_work_active,
                sobriety_date.isoformat() if sobriety_date else None,
                treatment_graduation_date.isoformat() if treatment_graduation_date else None,
                drug_of_choice,
                employment_notes,
                employment_status_current,
                employer_name,
                employment_type_current,
                monthly_income,
                current_job_start_date.isoformat() if current_job_start_date else None,
                continuous_employment_start_date.isoformat()
                if continuous_employment_start_date
                else None,
                previous_job_end_date.isoformat() if previous_job_end_date else None,
                upward_job_change,
                supervisor_name,
                supervisor_phone,
                unemployment_reason,
                job_change_notes,
                now,
                now,
                resident_id,
            ),
        )
    except Exception:
        flash("Unable to save profile changes.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    flash("Recovery profile updated.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
