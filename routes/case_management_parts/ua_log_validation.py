from __future__ import annotations

from typing import Any

from routes.case_management_parts.helpers import clean, parse_iso_date


def validate_ua_log_form(form) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []

    values: dict[str, Any] = {
        "ua_date": parse_iso_date(form.get("ua_date")),
        "result": clean(form.get("result")),
        "substances_detected": clean(form.get("substances_detected")),
        "notes": clean(form.get("notes")),
    }

    if not values["ua_date"]:
        errors.append("UA date is required.")

    return values, errors
