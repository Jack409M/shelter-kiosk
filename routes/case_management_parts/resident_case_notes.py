from __future__ import annotations

from routes.case_management_parts.resident_case_children import display_label
from routes.case_management_parts.resident_case_children import display_quantity_unit


SUMMARY_GROUP_ORDER = [
    "child",
    "medication",
    "service",
    "need_addressed",
    "need_outstanding",
    "employment",
    "sobriety",
    "advancement",
]

SUMMARY_GROUP_LABELS = {
    "child": "Children Changes",
    "medication": "Medication Changes",
    "service": "Services Provided",
    "need_addressed": "Needs Taken Care Of",
    "need_outstanding": "Needs Still Outstanding",
    "employment": "Employment Changes",
    "sobriety": "Sobriety Changes",
    "advancement": "Advancement Review",
}


def normalize_summary_row(row):
    return {
        "change_group": row.get("change_group"),
        "change_group_label": SUMMARY_GROUP_LABELS.get(
            row.get("change_group"),
            display_label(row.get("change_group")),
        ),
        "change_type": row.get("change_type"),
        "change_type_display": display_label(row.get("change_type")),
        "item_key": row.get("item_key"),
        "item_label": row.get("item_label") or "—",
        "old_value": row.get("old_value"),
        "new_value": row.get("new_value"),
        "detail": row.get("detail"),
        "sort_order": row.get("sort_order") or 0,
    }


def group_summary_rows(rows: list[dict]) -> list[dict]:
    grouped = {group_key: [] for group_key in SUMMARY_GROUP_ORDER}
    extra_groups: dict[str, list[dict]] = {}

    for row in rows:
        group_key = row.get("change_group") or ""
        if group_key in grouped:
            grouped[group_key].append(row)
        else:
            extra_groups.setdefault(group_key, []).append(row)

    result = []

    for group_key in SUMMARY_GROUP_ORDER:
        items = grouped.get(group_key, [])
        display_items = [item for item in items if item.get("change_type") != "snapshot"]
        if not display_items:
            continue
        result.append(
            {
                "group_key": group_key,
                "group_label": SUMMARY_GROUP_LABELS.get(group_key, display_label(group_key)),
                "items": display_items,
            }
        )

    for group_key in sorted(extra_groups.keys()):
        items = [item for item in extra_groups[group_key] if item.get("change_type") != "snapshot"]
        if not items:
            continue
        result.append(
            {
                "group_key": group_key,
                "group_label": SUMMARY_GROUP_LABELS.get(group_key, display_label(group_key)),
                "items": items,
            }
        )

    return result


def build_note_objects(notes_raw: list[dict], services_raw: list[dict], summary_rows_raw: list[dict]) -> tuple[list[dict], list[dict]]:
    services_by_note = {}
    for s in services_raw:
        note_id = s["case_manager_update_id"]
        service = {
            "service_type": s["service_type"],
            "service_date": s["service_date"],
            "quantity": s["quantity"],
            "unit": s["unit"],
            "quantity_display": display_quantity_unit(s["quantity"], s["unit"]),
            "notes": s["notes"],
        }
        services_by_note.setdefault(note_id, []).append(service)

    summary_by_note = {}
    for row in summary_rows_raw:
        note_id = row["case_manager_update_id"]
        summary_by_note.setdefault(note_id, []).append(normalize_summary_row(row))

    notes = []
    for n in notes_raw:
        note_id = n["id"]
        note_obj = dict(n)
        note_obj["ready_for_next_level_display"] = (
            display_label("yes") if n.get("ready_for_next_level") else (
                display_label("no") if n.get("ready_for_next_level") is not None else "—"
            )
        )
        note_obj["services"] = services_by_note.get(note_id, [])
        note_obj["summary_rows"] = summary_by_note.get(note_id, [])
        note_obj["summary_groups"] = group_summary_rows(note_obj["summary_rows"])
        notes.append(note_obj)

    return notes, services_raw
