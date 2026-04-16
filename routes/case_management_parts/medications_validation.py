from __future__ import annotations

from datetime import date
from typing import Any

from routes.case_management_parts.helpers import clean


def _parse_iso_date(value: str | None) -> str | None:
    cleaned = clean(value)
    if not cleaned:
        return None

    try:
        date.fromisoformat(cleaned)
    except ValueError:
        return None

    return cleaned


def validate_medication_form(form) -> tuple[dict[str, Any] | None, str | None]:
    medication_name = clean(form.get("medication_name"))
    dosage = clean(form.get("dosage"))
    frequency = clean(form.get("frequency"))
    purpose = clean(form.get("purpose"))
    prescribed_by = clean(form.get("prescribed_by"))
    started_on_raw = form.get("started_on")
    ended_on_raw = form.get("ended_on")
    notes = clean(form.get("notes"))
    is_active = (form.get("is_active") or "").strip().lower() == "yes"

    started_on = _parse_iso_date(started_on_raw)
    ended_on = _parse_iso_date(ended_on_raw)

    if not medication_name:
        return None, "Medication name is required."

    if started_on_raw and not started_on:
        return None, "Started on must be a valid date."

    if ended_on_raw and not ended_on:
        return None, "Ended on must be a valid date."

    if started_on and ended_on and ended_on < started_on:
        return None, "Ended on cannot be earlier than started on."

    data = {
        "medication_name": medication_name,
        "dosage": dosage,
        "frequency": frequency,
        "purpose": purpose,
        "prescribed_by": prescribed_by,
        "started_on": started_on,
        "ended_on": ended_on,
        "is_active": is_active,
        "notes": notes,
    }
    return data, None
