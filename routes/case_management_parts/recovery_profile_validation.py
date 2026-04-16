from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from routes.case_management_parts.helpers import (
    clean,
    digits_only,
    parse_int,
    parse_iso_date,
    parse_money,
)

ALLOWED_EMPLOYMENT_STATUS_VALUES = {"", "employed", "unemployed"}
ALLOWED_EMPLOYMENT_TYPE_VALUES = {"", "full_time", "part_time"}


def _yes_no_to_bool(value: str | None) -> bool | None:
    normalized = (value or "").strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


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


def validate_recovery_profile_form(form: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
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
