from __future__ import annotations

from typing import Any

from routes.case_management_parts.helpers import clean, parse_iso_date


def _yes_no_to_bool(value: Any) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"yes", "true", "1", "on", "y"}:
        return True
    if normalized in {"no", "false", "0", "off", "n"}:
        return False
    return None


def validate_income_support_form(form) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []

    values: dict[str, Any] = {
        "employment_income_1": clean(form.get("employment_income_1")),
        "employment_income_2": clean(form.get("employment_income_2")),
        "employment_income_3": clean(form.get("employment_income_3")),
        "ssi_ssdi_income": clean(form.get("ssi_ssdi_income")),
        "tanf_income": clean(form.get("tanf_income")),
        "alimony_income": clean(form.get("alimony_income")),
        "other_income": clean(form.get("other_income")),
        "other_income_description": clean(form.get("other_income_description")),
        "receives_snap_at_entry": clean(form.get("receives_snap_at_entry")),
        "employment_status_current": clean(form.get("employment_status_current")),
        "employer_name": clean(form.get("employer_name")),
        "employment_type_current": clean(form.get("employment_type_current")),
        "supervisor_name": clean(form.get("supervisor_name")),
        "supervisor_phone": clean(form.get("supervisor_phone")),
        "unemployment_reason": clean(form.get("unemployment_reason")),
        "employment_notes": clean(form.get("employment_notes")),
        "job_change_notes": clean(form.get("job_change_notes")),
        "upward_job_change": _yes_no_to_bool(form.get("upward_job_change")),
        "current_job_start_date": parse_iso_date(form.get("current_job_start_date")),
        "previous_job_end_date": parse_iso_date(form.get("previous_job_end_date")),
    }

    if not values["employment_status_current"]:
        errors.append("Employment status is required.")

    return values, errors
