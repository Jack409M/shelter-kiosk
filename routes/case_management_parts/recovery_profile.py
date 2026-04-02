from __future__ import annotations

from datetime import date

from flask import flash, redirect, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import parse_money
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql


def _clean_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _clean_date_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    return cleaned[:10]


def _parse_iso_date(value: str | None) -> date | None:
    cleaned = _clean_date_text(value)
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def _normalize_employment_status(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    if normalized in {"employed", "unemployed"}:
        return normalized
    return None


def _normalize_employment_type(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    if normalized in {"full_time", "part_time"}:
        return normalized
    return None


def _normalize_tristate_bool(value: str | None):
    normalized = (value or "").strip().lower()
    if normalized in {"yes", "true", "1", "on"}:
        return True
    if normalized in {"no", "false", "0", "off"}:
        return False
    return None


def _validate_profile_dates(payload: dict) -> str | None:
    level_start_date = _parse_iso_date(payload.get("level_start_date"))
    sobriety_date = _parse_iso_date(payload.get("sobriety_date"))
    treatment_graduation_date = _parse_iso_date(payload.get("treatment_graduation_date"))

    if payload.get("level_start_date") and not level_start_date:
        return "Level start date must be a valid date."

    if payload.get("sobriety_date") and not sobriety_date:
        return "Sobriety date must be a valid date."

    if payload.get("treatment_graduation_date") and not treatment_graduation_date:
        return "Treatment graduation date must be a valid date."

    if level_start_date and treatment_graduation_date and treatment_graduation_date < level_start_date:
        return "Treatment graduation date cannot be earlier than level start date."

    return None


def _build_profile_update_payload(resident: dict) -> tuple[dict, str | None]:
    current_step = resident.get("step_current")
    parsed_step = parse_int(request.form.get("step_current"))
    new_step = current_step if parsed_step is None else parsed_step

    if new_step is not None and (new_step < 1 or new_step > 12):
        return {}, "Step must be between 1 and 12."

    payload = {
        "program_level": _clean_text(request.form.get("program_level")),
        "level_start_date": _clean_date_text(request.form.get("level_start_date")),
        "sponsor_name": _clean_text(request.form.get("sponsor_name")),
        "sponsor_active": _normalize_tristate_bool(request.form.get("sponsor_active")),
        "sobriety_date": _clean_date_text(request.form.get("sobriety_date")),
        "drug_of_choice": _clean_text(request.form.get("drug_of_choice")),
        "treatment_graduation_date": _clean_date_text(request.form.get("treatment_graduation_date")),
        "employer_name": _clean_text(request.form.get("employer_name")),
        "employment_status_current": _normalize_employment_status(request.form.get("employment_status_current")),
        "employment_type_current": _normalize_employment_type(request.form.get("employment_type_current")),
        "supervisor_name": _clean_text(request.form.get("supervisor_name")),
        "supervisor_phone": _clean_text(request.form.get("supervisor_phone")),
        "unemployment_reason": _clean_text(request.form.get("unemployment_reason")),
        "employment_notes": _clean_text(request.form.get("employment_notes")),
        "monthly_income": parse_money(request.form.get("monthly_income")),
        "step_current": new_step,
        "step_work_active": _normalize_tristate_bool(request.form.get("step_work_active")),
    }

    if payload["employment_status_current"] == "unemployed":
        payload["employer_name"] = None
        payload["supervisor_name"] = None
        payload["supervisor_phone"] = None
        payload["employment_type_current"] = None
    else:
        payload["unemployment_reason"] = None

    date_error = _validate_profile_dates(payload)
    if date_error:
        return {}, date_error

    return payload, None


def _employment_fields_changed(resident: dict, payload: dict) -> bool:
    employment_fields = [
        "employment_status_current",
        "employment_type_current",
        "employer_name",
        "supervisor_name",
        "supervisor_phone",
        "unemployment_reason",
        "employment_notes",
        "monthly_income",
    ]
    return any(payload[field] != resident.get(field) for field in employment_fields)


def update_recovery_profile_view(resident_id: int):
    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident = db_fetchone(
        f"""
        SELECT
            id,
            program_level,
            level_start_date,
            sponsor_name,
            sponsor_active,
            step_current,
            step_work_active,
            employment_status_current,
            employment_type_current,
            employer_name,
            supervisor_name,
            supervisor_phone,
            unemployment_reason,
            employment_notes,
            monthly_income,
            sobriety_date,
            drug_of_choice,
            treatment_graduation_date
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    payload, validation_error = _build_profile_update_payload(resident)
    if validation_error:
        flash(validation_error, "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    step_changed = payload["step_current"] != resident.get("step_current")
    employment_changed = _employment_fields_changed(resident, payload)

    if step_changed:
        payload["step_changed_at"] = utcnow_iso()

    if employment_changed:
        payload["employment_updated_at"] = utcnow_iso()

    ordered_fields = [
        "program_level",
        "level_start_date",
        "sponsor_name",
        "sponsor_active",
        "sobriety_date",
        "drug_of_choice",
        "treatment_graduation_date",
        "employer_name",
        "employment_status_current",
        "employment_type_current",
        "supervisor_name",
        "supervisor_phone",
        "unemployment_reason",
        "employment_notes",
        "monthly_income",
        "step_current",
        "step_work_active",
        "employment_updated_at",
        "step_changed_at",
    ]

    set_clauses = []
    values = []

    for field_name in ordered_fields:
      if field_name not in payload:
          continue
      set_clauses.append(f"{field_name} = {ph}")
      values.append(payload[field_name])

    values.append(resident_id)

    db_execute(
        f"""
        UPDATE residents
        SET
            {", ".join(set_clauses)}
        WHERE id = {ph}
        """,
        tuple(values),
    )

    flash("Recovery profile updated.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
