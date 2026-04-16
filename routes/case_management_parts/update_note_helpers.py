from __future__ import annotations

from typing import Any

from routes.case_management_parts.update_needs import collect_need_updates
from routes.case_management_parts.update_utils import (
    clean_service_types,
    parse_grit,
    parse_quantity,
    yes_no_to_int,
)


def clean_text(value: object) -> str:
    return str(value or "").strip()


def yes_no_to_bool(value: object) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def collect_note_form_values(form) -> dict[str, Any]:
    meeting_date = clean_text(form.get("meeting_date"))
    notes = clean_text(form.get("notes"))
    progress_notes = clean_text(form.get("progress_notes"))
    setbacks_or_incidents = clean_text(form.get("setbacks_or_incidents"))
    action_items = clean_text(form.get("action_items"))
    overall_summary = clean_text(form.get("overall_summary"))
    ready_for_next_level = yes_no_to_bool(form.get("ready_for_next_level"))
    recommended_next_level = clean_text(form.get("recommended_next_level"))
    blocker_reason = clean_text(form.get("blocker_reason"))
    override_or_exception = clean_text(form.get("override_or_exception"))
    staff_review_note = clean_text(form.get("staff_review_note"))

    updated_grit_raw = clean_text(form.get("updated_grit"))
    updated_grit = parse_grit(updated_grit_raw)
    parenting_class_completed = yes_no_to_int(form.get("parenting_class_completed"))
    warrants_or_fines_paid = yes_no_to_int(form.get("warrants_or_fines_paid"))

    service_types = clean_service_types(form.getlist("service_type"))
    need_updates = collect_need_updates(form)

    return {
        "meeting_date": meeting_date,
        "notes": notes,
        "progress_notes": progress_notes,
        "setbacks_or_incidents": setbacks_or_incidents,
        "action_items": action_items,
        "overall_summary": overall_summary,
        "ready_for_next_level": ready_for_next_level,
        "recommended_next_level": recommended_next_level,
        "blocker_reason": blocker_reason,
        "override_or_exception": override_or_exception,
        "staff_review_note": staff_review_note,
        "updated_grit_raw": updated_grit_raw,
        "updated_grit": updated_grit,
        "parenting_class_completed": parenting_class_completed,
        "warrants_or_fines_paid": warrants_or_fines_paid,
        "service_types": service_types,
        "need_updates": need_updates,
    }


def has_structured_progress(values: dict[str, Any], *, include_needs: bool) -> bool:
    return (
        values["updated_grit"] is not None
        or values["parenting_class_completed"] is not None
        or values["warrants_or_fines_paid"] is not None
        or values["ready_for_next_level"] is not None
        or bool(values["recommended_next_level"])
        or bool(values["blocker_reason"])
        or bool(values["override_or_exception"])
        or bool(values["staff_review_note"])
        or bool(values["service_types"])
        or (include_needs and bool(values["need_updates"]))
    )


def service_form_payloads(form, service_types: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for service_type in service_types:
        service_note = clean_text(form.get(f"service_notes_{service_type}"))
        quantity = parse_quantity(form.get(f"quantity_{service_type}"))
        unit = clean_text(form.get(f"unit_{service_type}"))

        items.append(
            {
                "service_type": service_type,
                "service_note": service_note or None,
                "quantity": quantity,
                "unit": unit or None,
            }
        )

    return items
