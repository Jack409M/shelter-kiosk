from __future__ import annotations

from routes.case_management_parts.resident_case_children import display_label, display_quantity_unit

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
    "child": "Children Updates",
    "medication": "Medication Updates",
    "service": "Services Provided",
    "need_addressed": "Needs Resolved",
    "need_outstanding": "Outstanding Needs",
    "employment": "Employment Updates",
    "sobriety": "Recovery Updates",
    "advancement": "Advancement Review",
}


def _clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_summary_row(row):
    change_group = row.get("change_group")
    change_type = row.get("change_type")
    item_label = _clean_text(row.get("item_label")) or "—"

    return {
        "change_group": change_group,
        "change_group_label": SUMMARY_GROUP_LABELS.get(
            change_group,
            display_label(change_group),
        ),
        "change_type": change_type,
        "change_type_display": display_label(change_type),
        "item_key": row.get("item_key"),
        "item_label": item_label,
        "old_value": row.get("old_value"),
        "new_value": row.get("new_value"),
        "detail": row.get("detail"),
        "sort_order": row.get("sort_order") or 0,
    }


def _non_snapshot_items(items: list[dict]) -> list[dict]:
    return [item for item in items if item.get("change_type") != "snapshot"]


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
        display_items = _non_snapshot_items(items)
        if not display_items:
            continue

        if group_key == "need_addressed":
            all_resolved_items = [
                item for item in display_items if item.get("change_type") == "all_resolved"
            ]
            if all_resolved_items:
                result.append(
                    {
                        "group_key": group_key,
                        "group_label": SUMMARY_GROUP_LABELS.get(
                            group_key, display_label(group_key)
                        ),
                        "items": all_resolved_items,
                    }
                )
                continue

        result.append(
            {
                "group_key": group_key,
                "group_label": SUMMARY_GROUP_LABELS.get(group_key, display_label(group_key)),
                "items": display_items,
            }
        )

    for group_key in sorted(extra_groups.keys()):
        items = _non_snapshot_items(extra_groups[group_key])
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


def _build_services_by_note(services_raw: list[dict]) -> dict[int, list[dict]]:
    services_by_note: dict[int, list[dict]] = {}

    for service_row in services_raw:
        note_id = service_row["case_manager_update_id"]
        service = {
            "service_type": service_row["service_type"],
            "service_date": service_row["service_date"],
            "quantity": service_row["quantity"],
            "unit": service_row["unit"],
            "quantity_display": display_quantity_unit(service_row["quantity"], service_row["unit"]),
            "notes": service_row["notes"],
        }
        services_by_note.setdefault(note_id, []).append(service)

    return services_by_note


def _build_summary_by_note(summary_rows_raw: list[dict]) -> dict[int, list[dict]]:
    summary_by_note: dict[int, list[dict]] = {}

    for row in summary_rows_raw:
        note_id = row["case_manager_update_id"]
        summary_by_note.setdefault(note_id, []).append(normalize_summary_row(row))

    return summary_by_note


def _ready_for_next_level_display(note_row: dict) -> str:
    value = note_row.get("ready_for_next_level")

    if value is None:
        return "—"
    if value:
        return display_label("yes")
    return display_label("no")


def build_note_objects(
    notes_raw: list[dict],
    services_raw: list[dict],
    summary_rows_raw: list[dict],
) -> tuple[list[dict], list[dict]]:
    services_by_note = _build_services_by_note(services_raw)
    summary_by_note = _build_summary_by_note(summary_rows_raw)

    notes = []

    for note_row in notes_raw:
        note_id = note_row["id"]
        note_obj = dict(note_row)
        note_obj["ready_for_next_level_display"] = _ready_for_next_level_display(note_row)
        note_obj["services"] = services_by_note.get(note_id, [])
        note_obj["summary_rows"] = summary_by_note.get(note_id, [])
        note_obj["summary_groups"] = group_summary_rows(note_obj["summary_rows"])
        notes.append(note_obj)

    return notes, services_raw
