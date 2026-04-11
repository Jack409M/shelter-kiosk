from __future__ import annotations

from routes.case_management_parts.update_summary_helpers import display_snapshot_label
from routes.case_management_parts.update_summary_helpers import join_non_empty
from routes.case_management_parts.update_summary_helpers import normalize_detail
from routes.case_management_parts.update_summary_helpers import normalize_key
from routes.case_management_parts.update_summary_helpers import normalize_label
from routes.case_management_parts.update_summary_helpers import resolve_snapshot_change_type
from routes.case_management_parts.update_summary_helpers import resolve_snapshot_detail
from routes.case_management_parts.update_summary_helpers import resolve_snapshot_item_label
from routes.case_management_parts.update_summary_rows import insert_summary_row
from routes.case_management_parts.update_utils import clean_value
from routes.case_management_parts.update_utils import display_label
from routes.case_management_parts.update_utils import display_quantity_unit
from routes.case_management_parts.update_utils import parse_quantity


SummaryMap = dict[str, str]


def record_snapshot_change_group(
    case_manager_update_id: int,
    change_group: str,
    previous_snapshot: SummaryMap,
    current_snapshot: SummaryMap,
    label_map: dict[str, str] | None,
    added_label: str,
    removed_label: str,
    updated_label: str,
    created_at: str,
    starting_sort_order: int = 0,
) -> int:
    sort_order = starting_sort_order

    all_keys = sorted(
        set(previous_snapshot.keys()) | set(current_snapshot.keys()),
        key=lambda value: str(value),
    )

    for item_key in all_keys:
        old_value = previous_snapshot.get(item_key, "")
        new_value = current_snapshot.get(item_key, "")
        change_type = resolve_snapshot_change_type(old_value, new_value)

        if not change_type:
            continue

        insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group=change_group,
            change_type=change_type,
            item_key=normalize_key(item_key),
            item_label=normalize_label(
                resolve_snapshot_item_label(
                    item_key=item_key,
                    change_type=change_type,
                    label_map=label_map,
                    added_label=added_label,
                    removed_label=removed_label,
                    updated_label=updated_label,
                )
            ),
            old_value=normalize_detail(old_value),
            new_value=normalize_detail(new_value),
            detail=resolve_snapshot_detail(change_type, old_value, new_value),
            sort_order=sort_order,
            created_at=created_at,
        )
        sort_order += 1

    for item_key in sorted(current_snapshot.keys(), key=lambda value: str(value)):
        insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group=change_group,
            change_type="snapshot",
            item_key=normalize_key(item_key),
            item_label=normalize_label(
                display_snapshot_label(
                    item_key=item_key,
                    label_map=label_map,
                    fallback_label=item_key,
                )
            ),
            old_value=None,
            new_value=None,
            detail=normalize_detail(current_snapshot.get(item_key, "")),
            sort_order=sort_order,
            created_at=created_at,
        )
        sort_order += 1

    return sort_order


def record_service_summary(
    case_manager_update_id: int,
    service_types: list[str],
    form,
    created_at: str,
    starting_sort_order: int = 0,
) -> int:
    sort_order = starting_sort_order

    for service_type in service_types:
        service_note = clean_value(form.get(f"service_notes_{service_type}"))
        quantity = parse_quantity(form.get(f"quantity_{service_type}"))
        unit = clean_value(form.get(f"unit_{service_type}"))
        quantity_display = display_quantity_unit(quantity, unit or None)

        detail = join_non_empty(
            [
                quantity_display if quantity_display != "—" else "",
                service_note,
            ]
        )
        if not detail:
            detail = service_type

        insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group="service",
            change_type="provided",
            item_key=service_type.lower().replace(" ", "_"),
            item_label=service_type,
            old_value=None,
            new_value=None,
            detail=detail,
            sort_order=sort_order,
            created_at=created_at,
        )
        sort_order += 1

    return sort_order


def record_need_summary(
    case_manager_update_id: int,
    changed_needs: list[dict],
    outstanding_needs: list[dict],
    created_at: str,
    starting_sort_order: int = 0,
) -> int:
    sort_order = starting_sort_order

    for need in changed_needs:
        status = display_label(need.get("status"))
        resolution_note = clean_value(need.get("resolution_note"))
        detail = join_non_empty([status, resolution_note])

        insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group="need_addressed",
            change_type=need.get("status") or "addressed",
            item_key=normalize_key(need.get("need_key")),
            item_label=normalize_label(need.get("need_label")),
            old_value="Open",
            new_value=status,
            detail=detail or status,
            sort_order=sort_order,
            created_at=created_at,
        )
        sort_order += 1

    if outstanding_needs:
        for need in outstanding_needs:
            need_label = clean_value(need.get("need_label"))

            insert_summary_row(
                case_manager_update_id=case_manager_update_id,
                change_group="need_outstanding",
                change_type="open",
                item_key=normalize_key(need.get("need_key")),
                item_label=need_label or None,
                old_value=None,
                new_value="Open",
                detail=need_label or None,
                sort_order=sort_order,
                created_at=created_at,
            )
            sort_order += 1

        return sort_order

    insert_summary_row(
        case_manager_update_id=case_manager_update_id,
        change_group="need_addressed",
        change_type="all_resolved",
        item_key="all_identified_needs_resolved",
        item_label="Needs Review",
        old_value=None,
        new_value="Resolved",
        detail="All identified needs at intake have been resolved.",
        sort_order=sort_order,
        created_at=created_at,
    )
    sort_order += 1

    return sort_order
