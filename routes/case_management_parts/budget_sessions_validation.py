from __future__ import annotations

from typing import Any, Mapping

from routes.case_management_parts.helpers import clean, parse_iso_date


def validate_budget_session_form(form: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    data = {
        "session_date": clean(form.get("session_date")),
        "notes": clean(form.get("notes")),
    }

    errors: list[str] = []

    if not data["session_date"]:
        errors.append("Budget session date is required.")
    else:
        parsed_date = parse_iso_date(data["session_date"])
        if parsed_date is None:
            errors.append("Budget session date must be a valid date.")
        else:
            data["session_date"] = parsed_date.isoformat()

    return data, errors


__all__ = ["validate_budget_session_form"]
