from __future__ import annotations

from typing import Any

from routes.case_management_parts.helpers import clean

ALLOWED_DISPOSITION_ACTIONS = {
    "exit_now",
    "enroll_support",
}


def validate_l9_disposition_form(form: Any) -> tuple[dict[str, Any], list[str]]:
    data = {
        "disposition_action": clean(form.get("disposition_action")),
    }

    errors: list[str] = []

    if not data["disposition_action"]:
        errors.append("Level 9 disposition action is required.")
    elif data["disposition_action"] not in ALLOWED_DISPOSITION_ACTIONS:
        errors.append("Level 9 disposition action must be valid.")

    return data, errors
