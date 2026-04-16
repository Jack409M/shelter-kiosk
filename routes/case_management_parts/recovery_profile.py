"""
Resident identity and resident centered schema logic.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from flask import current_app, flash, g, redirect, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from db.schema_people import ensure_resident_child_income_supports_table
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    clean,
    digits_only,
    normalize_shelter_name,
    parse_int,
    parse_iso_date,
    parse_money,
    placeholder,
    shelter_equals_sql,
)

ALLOWED_EMPLOYMENT_STATUS_VALUES = {"", "employed", "unemployed"}
ALLOWED_EMPLOYMENT_TYPE_VALUES = {"", "full_time", "part_time"}


def _redirect_resident_case(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _redirect_case_index():
    return redirect(url_for("case_management.index"))


def _yes_no_to_bool(value: str | None) -> bool | None:
    normalized = (value or "").strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _load_resident_in_scope(resident_id: int):
    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    return db_fetchone(
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


def _build_recovery_profile_data(form: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "program_level": clean(form.get("program_level")),
        "level_start_date": clean(form.get("level_start_date")),
        "step_current": clean(form.get("step_current")),
        "sponsor_name": clean(form.get("sponsor_name")),
        "sponsor_active": form.get("sponsor_active"),
        "step_work_active": form.get("step_work_active"),
        "sobriety_date": clean(form.get("sobriety_date")),
        "treatment_graduation_date": clean(form.get("treatment_graduation_date")),
        "drug_of_choice": clean(form.get("drug_of_choice")),
        "employment_notes": clean(form.get("employment_notes")),
        "employment_status_current": clean(form.get("employment_status_current")),
        "employer_name": clean(form.get("employer_name")),
        "employment_type_current": clean(form.get("employment_type_current")),
        "monthly_income": clean(form.get("monthly_income")),
        "current_job_start_date": clean(form.get("current_job_start_date")),
        "continuous_employment_start_date": clean(form.get("continuous_employment_start_date")),
        "previous_job_end_date": clean(form.get("previous_job_end_date")),
        "upward_job_change": form.get("upward_job_change"),
        "supervisor_name": clean(form.get("supervisor_name")),
        "supervisor_phone": clean(form.get("supervisor_phone")),
        "unemployment_reason": clean(form.get("unemployment_reason")),
        "job_change_notes": clean(form.get("job_change_notes")),
    }


def _validate_optional_date_field(
    data: dict[str, Any],
    field_name: str,
    label: str,
    errors: list[str],
) -> date | None:
    raw_value = clean(data.get(field_name))
    parsed_value = parse_iso_date(raw_value)

    if raw_value and parsed_value is None:
        errors.append(f"{label} must be a valid date.")
        data[field_name] = None
        return None

    if parsed_value and parsed_value > date.today():
        errors.append(f"{label} cannot be in the future.")

    data[field_name] = parsed_value.isoformat() if parsed_value else None
    return parsed_value


def _validate_step_current(data: dict[str, Any], errors: list[str]) -> None:
    raw_value = clean(data.get("step_current"))
    parsed_value = parse_int(raw_value)

    if raw_value and parsed_value is None:
        errors.append("Current Step must be a whole number.")
    elif parsed_value is not None and not 1 <= parsed_value <= 12:
        errors.append("Current Step must be between 1 and 12.")

    data["step_current"] = parsed_value


def _validate_monthly_income(data: dict[str, Any], errors: list[str]) -> None:
    raw_value = clean(data.get("monthly_income"))
    parsed_value = parse_money(raw_value)

    if raw_value and parsed_value is None:
        errors.append("Income must be a valid dollar amount.")
    elif parsed_value is not None and parsed_value < 0:
        errors.append("Income cannot be negative.")

    data["monthly_income"] = parsed_value


def _validate_supervisor_phone(data: dict[str, Any], errors: list[str]) -> None:
    raw_value = clean(data.get("supervisor_phone"))
    if not raw_value:
        data["supervisor_phone"] = None
        return

    digits = digits_only(raw_value)
    if len(digits) < 10:
        errors.append("Supervisor Phone must contain at least 10 digits.")

    data["supervisor_phone"] = digits or None


def _validate_employment_fields(data: dict[str, Any], errors: list[str]) -> None:
    status_value = (clean(data.get("employment_status_current")) or "").lower()
    employment_type_value = (clean(data.get("employment_type_current")) or "").lower()

    if status_value not in ALLOWED_EMPLOYMENT_STATUS_VALUES:
        errors.append("Employment Status must be employed or unemployed.")

    if employment_type_value not in ALLOWED_EMPLOYMENT_TYPE_VALUES:
        errors.append("Employment Type must be full_time or part_time.")

    data["employment_status_current"] = status_value or None
    data["employment_type_current"] = employment_type_value or None

    if status_value == "employed":
        if not clean(data.get("employer_name")):
            errors.append("Employer is required when Employment Status is Employed.")

        if not employment_type_value:
            errors.append("Employment Type is required when Employment Status is Employed.")

        data["unemployment_reason"] = None
        return

    if status_value == "unemployed":
        if not clean(data.get("unemployment_reason")):
            errors.append("Unemployment Reason is required when Employment Status is Unemployed.")

        data["employer_name"] = None
        data["employment_type_current"] = None
        data["supervisor_name"] = None
        data["supervisor_phone"] = None
        return

    data["employer_name"] = None
    data["employment_type_current"] = None
    data["supervisor_name"] = None
    data["supervisor_phone"] = None
    data["unemployment_reason"] = None


def _validate_employment_date_order(data: dict[str, Any], errors: list[str]) -> None:
    current_job_start = parse_iso_date(data.get("current_job_start_date"))
    continuous_start = parse_iso_date(data.get("continuous_employment_start_date"))
    previous_job_end = parse_iso_date(data.get("previous_job_end_date"))

    if current_job_start and continuous_start and continuous_start > current_job_start:
        errors.append(
            "Continuous Employment Start Date cannot be after Current Job Start Date."
        )

    if previous_job_end and current_job_start and previous_job_end > current_job_start:
        errors.append("Previous Job End Date cannot be after Current Job Start Date.")


def _validate_recovery_profile_form(form: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    data = _build_recovery_profile_data(form)
    errors: list[str] = []

    data["sponsor_active"] = _yes_no_to_bool(clean(data.get("sponsor_active")))
    data["step_work_active"] = _yes_no_to_bool(clean(data.get("step_work_active")))
    data["upward_job_change"] = _yes_no_to_bool(clean(data.get("upward_job_change")))

    _validate_optional_date_field(data, "level_start_date", "Level Start Date", errors)
    _validate_optional_date_field(data, "sobriety_date", "Sobriety Date", errors)
    _validate_optional_date_field(
        data,
        "treatment_graduation_date",
        "Treatment Graduation Date",
        errors,
    )
    _validate_optional_date_field(
        data,
        "current_job_start_date",
        "Current Job Start Date",
        errors,
    )
    _validate_optional_date_field(
        data,
        "continuous_employment_start_date",
        "Continuous Employment Start Date",
        errors,
    )
    _validate_optional_date_field(
        data,
        "previous_job_end_date",
        "Previous Job End Date",
        errors,
    )

    _validate_step_current(data, errors)
    _validate_monthly_income(data, errors)
    _validate_supervisor_phone(data, errors)
    _validate_employment_fields(data, errors)
    _validate_employment_date_order(data, errors)

    return data, errors


def _log_recovery_profile_submission(resident_id: int) -> None:
    current_app.logger.info(
        "Recovery profile submit resident_id=%s employment_type_current=%r current_job_start_date=%r previous_job_end_date=%r upward_job_change=%r job_change_notes=%r sponsor_active=%r step_work_active=%r",
        resident_id,
        request.form.get("employment_type_current"),
        request.form.get("current_job_start_date"),
        request.form.get("previous_job_end_date"),
        request.form.get("upward_job_change"),
        request.form.get("job_change_notes"),
        request.form.get("sponsor_active"),
        request.form.get("step_work_active"),
    )


def _update_recovery_profile(resident_id: int, values: dict, now: str) -> None:
    ph = placeholder()

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
            values["program_level"],
            values["level_start_date"],
            values["step_current"],
            values["sponsor_name"],
            values["sponsor_active"],
            values["step_work_active"],
            values["sobriety_date"],
            values["treatment_graduation_date"],
            values["drug_of_choice"],
            values["employment_notes"],
            values["employment_status_current"],
            values["employer_name"],
            values["employment_type_current"],
            values["monthly_income"],
            values["current_job_start_date"],
            values["continuous_employment_start_date"],
            values["previous_job_end_date"],
            values["upward_job_change"],
            values["supervisor_name"],
            values["supervisor_phone"],
            values["unemployment_reason"],
            values["job_change_notes"],
            now,
            now,
            resident_id,
        ),
    )


def update_recovery_profile_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _redirect_resident_case(resident_id)

    ensure_resident_child_income_supports_table(g.get("db_kind"))

    resident = _load_resident_in_scope(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return _redirect_case_index()

    values, errors = _validate_recovery_profile_form(request.form)
    _log_recovery_profile_submission(resident_id)

    if errors:
        for error in errors:
            flash(error, "error")
        return _redirect_resident_case(resident_id)

    now = utcnow_iso()

    try:
        _update_recovery_profile(resident_id, values, now)
    except Exception:
        current_app.logger.exception(
            "Failed to save recovery profile for resident_id=%s",
            resident_id,
        )
        flash("Unable to save profile changes.", "error")
        return _redirect_resident_case(resident_id)

    flash("Recovery profile updated.", "success")
    return _redirect_resident_case(resident_id)
