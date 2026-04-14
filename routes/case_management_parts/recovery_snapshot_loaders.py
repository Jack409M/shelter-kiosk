from __future__ import annotations

from typing import Any

from core.db import db_fetchall, db_fetchone
from routes.case_management_parts.helpers import placeholder

Row = dict[str, Any]
Rows = list[Row]


def load_resident_profile(resident_id: int) -> Row:
    ph = placeholder()

    return (
        db_fetchone(
            f"""
        SELECT
            shelter,
            program_level,
            level_start_date,
            sponsor_name,
            sponsor_active,
            employer_name,
            employment_status_current,
            employment_type_current,
            supervisor_name,
            supervisor_phone,
            unemployment_reason,
            employment_notes,
            monthly_income,
            current_job_start_date,
            continuous_employment_start_date,
            previous_job_end_date,
            upward_job_change,
            job_change_notes,
            employment_updated_at,
            step_current,
            step_work_active,
            step_changed_at,
            sobriety_date,
            drug_of_choice,
            treatment_graduation_date,
            rad_classes_attended,
            rad_completed,
            rad_completed_at
        FROM residents
        WHERE id = {ph}
        LIMIT 1
        """,
            (resident_id,),
        )
        or {}
    )


def load_enrollment_baseline(enrollment_id: int | None) -> Row:
    if not enrollment_id:
        return {}

    ph = placeholder()

    row: Row = (
        db_fetchone(
            f"""
        SELECT entry_date
        FROM program_enrollments
        WHERE id = {ph}
        LIMIT 1
        """,
            (enrollment_id,),
        )
        or {}
    )

    intake_row: Row = (
        db_fetchone(
            f"""
        SELECT sobriety_date, treatment_grad_date
        FROM intake_assessments
        WHERE enrollment_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
            (enrollment_id,),
        )
        or {}
    )

    row["intake_sobriety_date"] = intake_row.get("sobriety_date")
    row["intake_treatment_grad_date"] = intake_row.get("treatment_grad_date")
    return row


def load_medications(resident_id: int, enrollment_id: int | None) -> Rows:
    ph = placeholder()
    active_true_sql = "TRUE" if ph == "%s" else "1"

    if enrollment_id is not None:
        return db_fetchall(
            f"""SELECT * FROM resident_medications
            WHERE resident_id = {ph} AND enrollment_id = {ph}
            AND COALESCE(is_active, TRUE) = {active_true_sql}
            ORDER BY COALESCE(updated_at, created_at) DESC, id DESC""",
            (resident_id, enrollment_id),
        )

    return db_fetchall(
        f"""SELECT * FROM resident_medications
        WHERE resident_id = {ph}
        AND COALESCE(is_active, TRUE) = {active_true_sql}
        ORDER BY COALESCE(updated_at, created_at) DESC, id DESC""",
        (resident_id,),
    )


def load_ua_rows(resident_id: int, enrollment_id: int | None) -> Rows:
    ph = placeholder()

    if enrollment_id is not None:
        return db_fetchall(
            f"""SELECT * FROM resident_ua_log
            WHERE resident_id = {ph} AND enrollment_id = {ph}
            ORDER BY ua_date DESC, id DESC""",
            (resident_id, enrollment_id),
        )

    return db_fetchall(
        f"""SELECT * FROM resident_ua_log
        WHERE resident_id = {ph}
        ORDER BY ua_date DESC, id DESC""",
        (resident_id,),
    )


def load_inspection_rows(resident_id: int, enrollment_id: int | None) -> Rows:
    ph = placeholder()

    if enrollment_id is not None:
        return db_fetchall(
            f"""SELECT * FROM resident_living_area_inspections
            WHERE resident_id = {ph} AND enrollment_id = {ph}
            ORDER BY inspection_date DESC, id DESC""",
            (resident_id, enrollment_id),
        )

    return db_fetchall(
        f"""SELECT * FROM resident_living_area_inspections
        WHERE resident_id = {ph}
        ORDER BY inspection_date DESC, id DESC""",
        (resident_id,),
    )


def load_budget_rows(resident_id: int, enrollment_id: int | None) -> Rows:
    ph = placeholder()

    if enrollment_id is not None:
        return db_fetchall(
            f"""SELECT * FROM resident_budget_sessions
            WHERE resident_id = {ph} AND enrollment_id = {ph}
            ORDER BY session_date DESC, id DESC""",
            (resident_id, enrollment_id),
        )

    return db_fetchall(
        f"""SELECT * FROM resident_budget_sessions
        WHERE resident_id = {ph}
        ORDER BY session_date DESC, id DESC""",
        (resident_id,),
    )


def load_writeup_rows(resident_id: int) -> Rows:
    ph = placeholder()

    return db_fetchall(
        f"""SELECT * FROM resident_writeups
        WHERE resident_id = {ph}
        ORDER BY incident_date DESC, id DESC""",
        (resident_id,),
    )
