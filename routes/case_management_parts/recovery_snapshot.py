from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.db import db_fetchall, db_fetchone
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


def load_recovery_snapshot(resident_id: int, enrollment_id: int | None):
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            program_level,
            sponsor_name,
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
            step_changed_at
        FROM residents
        WHERE id = {ph}
        LIMIT 1
        """,
        (resident_id,),
    ) or {}

    medications = db_fetchall(
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

    latest_ua = db_fetchone(
        f"""
        SELECT
            ua_date,
            result,
            substances_detected,
            notes
        FROM resident_ua_log
        WHERE resident_id = {ph}
        ORDER BY ua_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    latest_inspection = db_fetchone(
        f"""
        SELECT
            inspection_date,
            passed,
            notes
        FROM resident_living_area_inspections
        WHERE resident_id = {ph}
        ORDER BY inspection_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    latest_budget_session = db_fetchone(
        f"""
        SELECT
            session_date,
            notes
        FROM resident_budget_sessions
        WHERE resident_id = {ph}
        ORDER BY session_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    step_changed_at = resident.get("step_changed_at")
    step_days = _days_since(step_changed_at)
    employment_updated_at = resident.get("employment_updated_at")
    employment_days = _days_since(employment_updated_at)

    medication_items = []
    for med in medications or []:
        medication_items.append(
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

    snapshot = {
        "program_level": resident.get("program_level"),
        "sponsor_name": resident.get("sponsor_name"),
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
        "employment_days": employment_days,
        "step_current": resident.get("step_current"),
        "step_changed_at": step_changed_at,
        "step_days": step_days,
        "medications": medication_items,
        "medication_count": len(medication_items),
        "latest_ua": None,
        "latest_inspection": None,
        "latest_budget_session": None,
    }

    if latest_ua:
        snapshot["latest_ua"] = {
            "ua_date": latest_ua.get("ua_date"),
            "result": latest_ua.get("result"),
            "substances_detected": latest_ua.get("substances_detected"),
            "notes": latest_ua.get("notes"),
        }

    if latest_inspection:
        snapshot["latest_inspection"] = {
            "inspection_date": latest_inspection.get("inspection_date"),
            "passed": latest_inspection.get("passed"),
            "passed_display": _bool_display(latest_inspection.get("passed")),
            "notes": latest_inspection.get("notes"),
        }

    if latest_budget_session:
        snapshot["latest_budget_session"] = {
            "session_date": latest_budget_session.get("session_date"),
            "notes": latest_budget_session.get("notes"),
        }

    return snapshot
