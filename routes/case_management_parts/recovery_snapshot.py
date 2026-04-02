from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.db import db_fetchall, db_fetchone
from routes.case_management_parts.helpers import fetch_current_enrollment_id_for_resident
from routes.case_management_parts.helpers import placeholder


def _parse_dateish(value: Any):
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _days_since(value: Any):
    parsed = _parse_dateish(value)
    if not parsed:
        return None

    days = (date.today() - parsed).days
    if days < 0:
        days = 0
    return days


def _money_display(value: Any) -> str:
    if value in (None, ""):
        return "—"

    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)

    return f"${amount:,.2f}"


def _bool_display(value: Any) -> str:
    if value is None:
        return "—"
    return "Yes" if bool(value) else "No"


def _employment_status_display(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "—"
    if normalized == "employed":
        return "Employed"
    if normalized == "unemployed":
        return "Unemployed"
    return str(value)


def _employment_type_display(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "—"
    if normalized == "full_time":
        return "Full Time"
    if normalized == "part_time":
        return "Part Time"
    return str(value).replace("_", " ").title()


def _result_display(value: Any) -> str:
    normalized = str(value or "").strip()
    return normalized or "—"


def _medication_items(rows):
    items = []
    for med in rows or []:
        items.append(
            {
                "id": med.get("id"),
                "medication_name": med.get("medication_name"),
                "dosage": med.get("dosage"),
                "frequency": med.get("frequency"),
                "purpose": med.get("purpose"),
                "prescribed_by": med.get("prescribed_by"),
                "started_on": med.get("started_on"),
                "ended_on": med.get("ended_on"),
                "is_active": med.get("is_active"),
                "notes": med.get("notes"),
            }
        )
    return items


def _ua_items(rows):
    items = []
    for row in rows or []:
        items.append(
            {
                "id": row.get("id"),
                "ua_date": row.get("ua_date"),
                "result": row.get("result"),
                "result_display": _result_display(row.get("result")),
                "substances_detected": row.get("substances_detected"),
                "notes": row.get("notes"),
            }
        )
    return items


def _inspection_items(rows):
    items = []
    for row in rows or []:
        items.append(
            {
                "id": row.get("id"),
                "inspection_date": row.get("inspection_date"),
                "passed": row.get("passed"),
                "passed_display": _bool_display(row.get("passed")),
                "notes": row.get("notes"),
            }
        )
    return items


def _budget_items(rows):
    items = []
    for row in rows or []:
        items.append(
            {
                "id": row.get("id"),
                "session_date": row.get("session_date"),
                "notes": row.get("notes"),
            }
        )
    return items


def _load_resident_profile(resident_id: int):
    ph = placeholder()

    return db_fetchone(
        f"""
        SELECT
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
            employment_updated_at,
            step_current,
            step_work_active,
            step_changed_at,
            sobriety_date,
            drug_of_choice,
            treatment_graduation_date
        FROM residents
        WHERE id = {ph}
        LIMIT 1
        """,
        (resident_id,),
    ) or {}


def _load_enrollment_baseline(enrollment_id: int | None):
    if not enrollment_id:
        return {}

    ph = placeholder()

    row = db_fetchone(
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

    row["intake_sobriety_date"] = intake_row.get("sobriety_date")
    row["intake_treatment_grad_date"] = intake_row.get("treatment_grad_date")
    return row


def _load_medications(resident_id: int, enrollment_id: int | None):
    ph = placeholder()

    if enrollment_id is not None:
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
            WHERE resident_id = {ph}
              AND enrollment_id = {ph}
              AND COALESCE(is_active, TRUE) = {('TRUE' if ph == '%s' else '1')}
            ORDER BY
                COALESCE(updated_at, created_at) DESC,
                id DESC
            """,
            (resident_id, enrollment_id),
        )

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
        WHERE resident_id = {ph}
          AND COALESCE(is_active, TRUE) = {('TRUE' if ph == '%s' else '1')}
        ORDER BY
            COALESCE(updated_at, created_at) DESC,
            id DESC
        """,
        (resident_id,),
    )


def _load_ua_rows(resident_id: int, enrollment_id: int | None):
    ph = placeholder()

    if enrollment_id is not None:
        return db_fetchall(
            f"""
            SELECT
                id,
                ua_date,
                result,
                substances_detected,
                notes
            FROM resident_ua_log
            WHERE resident_id = {ph}
              AND enrollment_id = {ph}
            ORDER BY ua_date DESC, id DESC
            """,
            (resident_id, enrollment_id),
        )

    return db_fetchall(
        f"""
        SELECT
            id,
            ua_date,
            result,
            substances_detected,
            notes
        FROM resident_ua_log
        WHERE resident_id = {ph}
        ORDER BY ua_date DESC, id DESC
        """,
        (resident_id,),
    )


def _load_inspection_rows(resident_id: int, enrollment_id: int | None):
    ph = placeholder()

    if enrollment_id is not None:
        return db_fetchall(
            f"""
            SELECT
                id,
                inspection_date,
                passed,
                notes
            FROM resident_living_area_inspections
            WHERE resident_id = {ph}
              AND enrollment_id = {ph}
            ORDER BY inspection_date DESC, id DESC
            """,
            (resident_id, enrollment_id),
        )

    return db_fetchall(
        f"""
        SELECT
            id,
            inspection_date,
            passed,
            notes
        FROM resident_living_area_inspections
        WHERE resident_id = {ph}
        ORDER BY inspection_date DESC, id DESC
        """,
        (resident_id,),
    )


def _load_budget_rows(resident_id: int, enrollment_id: int | None):
    ph = placeholder()

    if enrollment_id is not None:
        return db_fetchall(
            f"""
            SELECT
                id,
                session_date,
                notes
            FROM resident_budget_sessions
            WHERE resident_id = {ph}
              AND enrollment_id = {ph}
            ORDER BY session_date DESC, id DESC
            """,
            (resident_id, enrollment_id),
        )

    return db_fetchall(
        f"""
        SELECT
            id,
            session_date,
            notes
        FROM resident_budget_sessions
        WHERE resident_id = {ph}
        ORDER BY session_date DESC, id DESC
        """,
        (resident_id,),
    )


def _normalize_level_start_date(resident: dict, enrollment_baseline: dict) -> Any:
    return resident.get("level_start_date") or enrollment_baseline.get("entry_date")


def _normalize_sobriety_date(resident: dict, enrollment_baseline: dict) -> Any:
    return (
        resident.get("sobriety_date")
        or enrollment_baseline.get("intake_sobriety_date")
        or enrollment_baseline.get("entry_date")
    )


def _normalize_treatment_graduation_date(resident: dict, enrollment_baseline: dict) -> Any:
    return resident.get("treatment_graduation_date") or enrollment_baseline.get("intake_treatment_grad_date")


def load_recovery_snapshot(resident_id: int, enrollment_id: int | None):
    current_enrollment_id = enrollment_id or fetch_current_enrollment_id_for_resident(resident_id)

    resident = _load_resident_profile(resident_id)
    enrollment_baseline = _load_enrollment_baseline(current_enrollment_id)

    level_start_date = _normalize_level_start_date(resident, enrollment_baseline)
    sobriety_date = _normalize_sobriety_date(resident, enrollment_baseline)
    treatment_graduation_date = _normalize_treatment_graduation_date(resident, enrollment_baseline)

    step_changed_at = resident.get("step_changed_at")
    employment_updated_at = resident.get("employment_updated_at")

    medications_raw = _load_medications(resident_id, current_enrollment_id)
    ua_rows_raw = _load_ua_rows(resident_id, current_enrollment_id)
    inspection_rows_raw = _load_inspection_rows(resident_id, current_enrollment_id)
    budget_rows_raw = _load_budget_rows(resident_id, current_enrollment_id)

    medication_items = _medication_items(medications_raw)
    ua_items = _ua_items(ua_rows_raw)
    inspection_items = _inspection_items(inspection_rows_raw)
    budget_items = _budget_items(budget_rows_raw)

    return {
        "program_level": resident.get("program_level") or "1",
        "level_start_date": level_start_date,
        "days_on_level": _days_since(level_start_date),
        "sponsor_name": resident.get("sponsor_name"),
        "sponsor_active": resident.get("sponsor_active"),
        "sponsor_active_display": _bool_display(resident.get("sponsor_active")),
        "employer_name": resident.get("employer_name"),
        "employment_status_current": resident.get("employment_status_current"),
        "employment_status_display": _employment_status_display(resident.get("employment_status_current")),
        "employment_type_current": resident.get("employment_type_current"),
        "employment_type_display": _employment_type_display(resident.get("employment_type_current")),
        "supervisor_name": resident.get("supervisor_name"),
        "supervisor_phone": resident.get("supervisor_phone"),
        "unemployment_reason": resident.get("unemployment_reason"),
        "employment_notes": resident.get("employment_notes"),
        "monthly_income": resident.get("monthly_income"),
        "monthly_income_display": _money_display(resident.get("monthly_income")),
        "employment_updated_at": employment_updated_at,
        "employment_days": _days_since(employment_updated_at),
        "step_current": resident.get("step_current"),
        "step_work_active": resident.get("step_work_active"),
        "step_work_active_display": _bool_display(resident.get("step_work_active")),
        "step_changed_at": step_changed_at,
        "step_days": _days_since(step_changed_at),
        "sobriety_date": sobriety_date,
        "days_sober_today": _days_since(sobriety_date),
        "days_sober_at_entry": None,
        "drug_of_choice": resident.get("drug_of_choice"),
        "treatment_graduation_date": treatment_graduation_date,
        "medications": medication_items,
        "medication_count": len(medication_items),
        "ua_rows": ua_items,
        "inspection_rows": inspection_items,
        "budget_rows": budget_items,
        "latest_ua": ua_items[0] if ua_items else None,
        "latest_inspection": inspection_items[0] if inspection_items else None,
        "latest_budget_session": budget_items[0] if budget_items else None,
    }
