from __future__ import annotations

from typing import Any

from core.db import db_fetchall
from core.db import db_fetchone
from routes.case_management_parts.helpers import placeholder


type Row = dict[str, Any]
type RowList = list[Row]


def _placeholder() -> str:
    return placeholder()


def _active_true_sql(ph: str) -> str:
    return "TRUE" if ph == "%s" else "1"


def _fetch_rows_for_resident(
    *,
    resident_id: int,
    enrollment_id: int | None,
    table: str,
    select_sql: str,
    order_by_sql: str,
) -> RowList:
    ph = _placeholder()

    where_lines = [f"resident_id = {ph}"]
    params: list[Any] = [resident_id]

    if enrollment_id is not None:
        where_lines.append(f"enrollment_id = {ph}")
        params.append(enrollment_id)

    return db_fetchall(
        f"""
        SELECT
            {select_sql}
        FROM {table}
        WHERE {" AND ".join(where_lines)}
        ORDER BY {order_by_sql}
        """,
        tuple(params),
    )


def load_resident_profile(resident_id: int) -> Row:
    ph = _placeholder()

    return db_fetchone(
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
    ) or {}


def load_enrollment_baseline(enrollment_id: int | None) -> Row:
    if not enrollment_id:
        return {}

    ph = _placeholder()

    enrollment_row = db_fetchone(
        f"""
        SELECT
            entry_date
        FROM program_enrollments
        WHERE id = {ph}
        LIMIT 1
        """,
        (enrollment_id,),
    ) or {}

    intake_row = db_fetchone(
        f"""
        SELECT
            sobriety_date,
            treatment_grad_date
        FROM intake_assessments
        WHERE enrollment_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    ) or {}

    return {
        **enrollment_row,
        "intake_sobriety_date": intake_row.get("sobriety_date"),
        "intake_treatment_grad_date": intake_row.get("treatment_grad_date"),
    }


def load_medications(resident_id: int, enrollment_id: int | None) -> RowList:
    ph = _placeholder()
    active_true_sql = _active_true_sql(ph)

    where_lines = [
        f"resident_id = {ph}",
        f"COALESCE(is_active, TRUE) = {active_true_sql}",
    ]
    params: list[Any] = [resident_id]

    if enrollment_id is not None:
        where_lines.insert(1, f"enrollment_id = {ph}")
        params.append(enrollment_id)

    return db_fetchall(
        f"""
        SELECT
            id,
            medication_name,
            dosage,
            frequency,
            purpose,
            prescribed_by,
            started_on,
            ended_on,
            is_active,
            notes,
            updated_at,
            created_at
        FROM resident_medications
        WHERE {" AND ".join(where_lines)}
        ORDER BY
            COALESCE(updated_at, created_at) DESC,
            id DESC
        """,
        tuple(params),
    )


def load_ua_rows(resident_id: int, enrollment_id: int | None) -> RowList:
    return _fetch_rows_for_resident(
        resident_id=resident_id,
        enrollment_id=enrollment_id,
        table="resident_ua_log",
        select_sql="""
            id,
            ua_date,
            result,
            substances_detected,
            notes
        """,
        order_by_sql="ua_date DESC, id DESC",
    )


def load_inspection_rows(resident_id: int, enrollment_id: int | None) -> RowList:
    return _fetch_rows_for_resident(
        resident_id=resident_id,
        enrollment_id=enrollment_id,
        table="resident_living_area_inspections",
        select_sql="""
            id,
            inspection_date,
            passed,
            notes
        """,
        order_by_sql="inspection_date DESC, id DESC",
    )


def load_budget_rows(resident_id: int, enrollment_id: int | None) -> RowList:
    return _fetch_rows_for_resident(
        resident_id=resident_id,
        enrollment_id=enrollment_id,
        table="resident_budget_sessions",
        select_sql="""
            id,
            session_date,
            notes
        """,
        order_by_sql="session_date DESC, id DESC",
    )


def load_writeup_rows(resident_id: int) -> RowList:
    ph = _placeholder()

    try:
        return db_fetchall(
            f"""
            SELECT
                id,
                incident_date,
                category,
                severity,
                status,
                summary,
                created_at,
                updated_at
            FROM resident_writeups
            WHERE resident_id = {ph}
            ORDER BY incident_date DESC, id DESC
            """,
            (resident_id,),
        )
    except Exception:
        return []
