from __future__ import annotations

from datetime import UTC, datetime

from core.db import db_fetchone
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident


def row_value(row, key: str, index: int | None = None, default=None):
    if row is None:
        return default

    if isinstance(row, dict):
        value = row.get(key, default)
        return default if value is None else value

    try:
        value = row[key]
        return default if value is None else value
    except Exception as e:
        from flask import current_app
        current_app.logger.exception("auto-logged exception")

    if index is not None:
        try:
            value = row[index]
            return default if value is None else value
        except Exception as e:
            from flask import current_app
            current_app.logger.exception("auto-logged exception")

    return default


def load_resident_for_shelter(resident_id: int, shelter: str, sql_selector, shelter_equals_sql):
    resident = db_fetchone(
        sql_selector(
            f"""
            SELECT
                id,
                first_name,
                last_name,
                shelter AS resident_shelter,
                is_active,
                resident_code,
                birth_year,
                phone,
                email,
                emergency_contact_name,
                emergency_contact_relationship,
                emergency_contact_phone,
                medical_alerts,
                medical_notes
            FROM residents
            WHERE id = %s
              AND {shelter_equals_sql("shelter")}
            LIMIT 1
            """,
            f"""
            SELECT
                id,
                first_name,
                last_name,
                shelter AS resident_shelter,
                is_active,
                resident_code,
                birth_year,
                phone,
                email,
                emergency_contact_name,
                emergency_contact_relationship,
                emergency_contact_phone,
                medical_alerts,
                medical_notes
            FROM residents
            WHERE id = ?
              AND {shelter_equals_sql("shelter")}
            LIMIT 1
            """,
        ),
        (resident_id, shelter),
    )

    if not resident:
        return None

    enrollment = fetch_current_enrollment_for_resident(
        resident_id,
        shelter=shelter,
        columns="""
            id AS enrollment_id,
            shelter AS enrollment_shelter,
            program_status,
            entry_date,
            exit_date,
            (
                SELECT ia.sobriety_date
                FROM intake_assessments ia
                WHERE ia.enrollment_id = program_enrollments.id
                ORDER BY id DESC
                LIMIT 1
            ) AS sobriety_date,
            (
                SELECT ia.days_sober_at_entry
                FROM intake_assessments ia
                WHERE ia.enrollment_id = program_enrollments.id
                ORDER BY id DESC
                LIMIT 1
            ) AS days_sober_at_entry
        """,
    )

    merged = dict(resident)
    if enrollment:
        merged.update(dict(enrollment))
    else:
        merged.update(
            {
                "enrollment_id": None,
                "enrollment_shelter": None,
                "program_status": None,
                "entry_date": None,
                "exit_date": None,
                "sobriety_date": None,
                "days_sober_at_entry": None,
            }
        )

    return merged


def next_appointment_for_enrollment(enrollment_id: int, sql_selector):
    today_iso = datetime.now(UTC).date().isoformat()

    row = db_fetchone(
        sql_selector(
            """
            SELECT
                appointment_date,
                appointment_type,
                notes,
                reminder_sent,
                created_at
            FROM appointments
            WHERE enrollment_id = %s
              AND appointment_date IS NOT NULL
              AND appointment_date >= %s
            ORDER BY
                appointment_date ASC,
                id ASC
            LIMIT 1
            """,
            """
            SELECT
                appointment_date,
                appointment_type,
                notes,
                reminder_sent,
                created_at
            FROM appointments
            WHERE enrollment_id = ?
              AND appointment_date IS NOT NULL
              AND appointment_date >= ?
            ORDER BY
                appointment_date ASC,
                id ASC
            LIMIT 1
            """,
        ),
        (enrollment_id, today_iso),
    )

    if row:
        return row

    return db_fetchone(
        sql_selector(
            """
            SELECT
                appointment_date,
                appointment_type,
                notes,
                reminder_sent,
                created_at
            FROM appointments
            WHERE enrollment_id = %s
              AND appointment_date IS NOT NULL
            ORDER BY
                appointment_date DESC,
                id DESC
            LIMIT 1
            """,
            """
            SELECT
                appointment_date,
                appointment_type,
                notes,
                reminder_sent,
                created_at
            FROM appointments
            WHERE enrollment_id = ?
              AND appointment_date IS NOT NULL
            ORDER BY
                appointment_date DESC,
                id DESC
            LIMIT 1
            """,
        ),
        (enrollment_id,),
    )


def resident_enrollment_for_shelter(
    resident_id: int, shelter: str, sql_selector, shelter_equals_sql
):
    resident = db_fetchone(
        sql_selector(
            f"""
            SELECT
                id
            FROM residents
            WHERE id = %s
              AND {shelter_equals_sql("shelter")}
            LIMIT 1
            """,
            f"""
            SELECT
                id
            FROM residents
            WHERE id = ?
              AND {shelter_equals_sql("shelter")}
            LIMIT 1
            """,
        ),
        (resident_id, shelter),
    )

    if not resident:
        return None

    enrollment = fetch_current_enrollment_for_resident(
        resident_id,
        shelter=shelter,
        columns="id AS enrollment_id",
    )

    merged = dict(resident)
    merged["enrollment_id"] = row_value(enrollment, "enrollment_id", 0)
    return merged


def load_enrollment_context_for_shelter(
    resident_id: int, shelter: str, sql_selector, shelter_equals_sql
) -> dict[str, object]:
    resident = resident_enrollment_for_shelter(
        resident_id, shelter, sql_selector, shelter_equals_sql
    )
    enrollment_id = row_value(resident, "enrollment_id", 1) if resident else None

    return {
        "resident": resident,
        "enrollment_id": enrollment_id,
    }
