from __future__ import annotations

from typing import Any, Mapping

from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import clean, parse_iso_date, parse_money


def validate_followup_form(
    form: Mapping[str, Any],
    followup_type: str,
) -> tuple[dict[str, Any], list[str]]:
    data = {
        "followup_date": clean(form.get("followup_date")),
        "followup_type": followup_type,
        "income_at_followup": clean(form.get("income_at_followup")),
        "sober_at_followup": clean(form.get("sober_at_followup")),
        "notes": clean(form.get("notes")),
    }

    errors: list[str] = []

    followup_date = parse_iso_date(data["followup_date"])
    if data["followup_date"] and followup_date is None:
        errors.append("Follow up date must be a valid date.")
    data["followup_date"] = followup_date.isoformat() if followup_date else utcnow_iso()[:10]

    income = parse_money(data["income_at_followup"])
    if data["income_at_followup"] and income is None:
        errors.append("Income at Follow Up must be a valid number.")
    if income is not None and income < 0:
        errors.append("Income at Follow Up cannot be negative.")
    data["income_at_followup"] = income

    if data["sober_at_followup"] not in {None, "", "yes", "no"}:
        errors.append("Sober at Follow Up must be Yes or No.")

    return data, errors


__all__ = ["validate_followup_form"]
