from __future__ import annotations

from core.db import db_execute, db_fetchall, db_fetchone
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.update_needs import current_open_needs
from routes.case_management_parts.update_snapshots import get_current_advancement_snapshot
from routes.case_management_parts.update_snapshots import get_current_children_snapshot
from routes.case_management_parts.update_snapshots import get_current_employment_snapshot
from routes.case_management_parts.update_snapshots import get_current_medication_snapshot
from routes.case_management_parts.update_snapshots import get_current_sobriety_snapshot
from routes.case_management_parts.update_snapshots import load_previous_snapshot_map
from routes.case_management_parts.update_utils import ADVANCEMENT_BOOL_FIELD_LABELS
from routes.case_management_parts.update_utils import ADVANCEMENT_TEXT_FIELD_LABELS
from routes.case_management_parts.update_utils import EMPLOYMENT_FIELD_LABELS
from routes.case_management_parts.update_utils import MEETING_TEXT_FIELD_LABELS
from routes.case_management_parts.update_utils import SOBRIETY_FIELD_LABELS
from routes.case_management_parts.update_utils import clean_value
from routes.case_management_parts.update_utils import display_label
from routes.case_management_parts.update_utils import display_quantity_unit
from routes.case_management_parts.update_utils import parse_quantity


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _join_non_empty(parts: list[str]) -> str:
    cleaned = [part.strip() for part in parts if part and str(part).strip()]
    return " | ".join(cleaned)


def insert_summary_row(
    case_manager_update_id: int,
    change_group: str,
    change_type: str,
    item_key: str | None,
    item_label: str | None,
    old_value: str | None,
    new_value: str | None,
    detail: str | None,
    sort_order: int,
    created_at: str,
) -> None:
    ph = placeholder()

    db_execute(
        f"""
        INSERT INTO case_manager_update_summary
        (
            case_manager_update_id,
            change_group,
            change_type,
            item_key,
            item_label,
            old_value,
            new_value,
            detail,
            sort_order,
            created_at
        )
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
        """,
        (
            case_manager_update_id,
            change_group,
            change_type,
            item_key,
            item_label,
            old_value,
            new_value,
            detail,
            sort_order,
            created_at,
        ),
    )


def delete_summary_rows_by_group(case_manager_update_id: int, change_groups: list[str]) -> None:
    if not change_groups:
        return

    ph = placeholder()
    group_placeholders = ",".join([ph] * len(change_groups))

    db_execute(
        f"""
        DELETE FROM case_manager_update_summary
        WHERE case_manager_update_id = {ph}
          AND change_group IN ({group_placeholders})
        """,
        (case_manager_update_id, *change_groups),
    )


def get_next_summary_sort_order(case_manager_update_id: int) -> int:
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT COALESCE(MAX(sort_order), -1) AS max_sort_order
        FROM case_manager_update_summary
        WHERE case_manager_update_id = {ph}
        """,
        (case_manager_update_id,),
    )

    if not row:
        return 0

    max_sort_order = row["max_sort_order"]
    if max_sort_order is None:
        return 0

    return int(max_sort_order) + 1


def get_previous_note_id(
    enrollment_id: int,
    current_note_id: int,
    current_meeting_date: str | None,
) -> int | None:
    ph = placeholder()

    if current_meeting_date:
        row = db_fetchone(
            f"""
            SELECT id
            FROM case_manager_updates
            WHERE enrollment_id = {ph}
              AND (
                    meeting_date < {ph}
                    OR (meeting_date = {ph} AND id < {ph})
                  )
            ORDER BY meeting_date DESC, id DESC
            LIMIT 1
            """,
            (enrollment_id, current_meeting_date, current_meeting_date, current_note_id),
        )
        return row["id"] if row else None

    row = db_fetchone(
        f"""
        SELECT id
        FROM case_manager_updates
        WHERE enrollment_id = {ph}
          AND id < {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id, current_note_id),
    )

    return row["id"] if row else None


def record_snapshot_change_group(
    case_manager_update_id: int,
    change_group: str,
    previous_snapshot: dict[str, str],
    current_snapshot: dict[str, str],
    label_map: dict[str, str] | None,
    added_label: str,
    removed_label: str,
    updated_label: str,
    created_at: str,
    starting_sort_order: int = 0,
) -> int:
    sort_order = starting_sort_order

    all_keys = sorted(set(previous_snapshot.keys()) | set(current_snapshot.keys()), key=lambda x: str(x))

    for item_key in all_keys:
        old_value = previous_snapshot.get(item_key, "")
        new_value = current_snapshot.get(item_key, "")

        if old_value == new_value:
            continue

        item_label = label_map[item_key] if label_map and item_key in label_map else item_key

        if old_value and not new_value:
            change_type = "removed"
            display_name = removed_label if not label_map else item_label
            detail = old_value
        elif not old_value and new_value:
            change_type = "added"
            display_name = added_label if not label_map else item_label
            detail = new_value
        else:
            change_type = "updated"
            display_name = updated_label if not label_map else item_label
            detail = new_value

        insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group=change_group,
            change_type=change_type,
            item_key=item_key,
            item_label=display_name,
            old_value=old_value or None,
            new_value=new_value or None,
            detail=detail or None,
            sort_order=sort_order,
            created_at=created_at,
        )
        sort_order += 1

    for item_key in sorted(current_snapshot.keys(), key=lambda x: str(x)):
        insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group=change_group,
            change_type="snapshot",
            item_key=item_key,
            item_label=(label_map[item_key] if label_map and item_key in label_map else item_key),
            old_value=None,
            new_value=None,
            detail=current_snapshot.get(item_key, ""),
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
        service_note = _clean_text(form.get(f"service_notes_{service_type}"))
        quantity = parse_quantity(form.get(f"quantity_{service_type}"))
        unit = _clean_text(form.get(f"unit_{service_type}"))
        quantity_display = display_quantity_unit(quantity, unit or None)

        detail = _join_non_empty([quantity_display if quantity_display != "—" else "", service_note])
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

        detail = _join_non_empty([status, resolution_note])

        insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group="need_addressed",
            change_type=need.get("status") or "addressed",
            item_key=need.get("need_key"),
            item_label=need.get("need_label"),
            old_value="Open",
            new_value=status,
            detail=detail or status,
            sort_order=sort_order,
            created_at=created_at,
        )
        sort_order += 1

    if outstanding_needs:
        for need in outstanding_needs:
            need_label = need.get("need_label")
            insert_summary_row(
                case_manager_update_id=case_manager_update_id,
                change_group="need_outstanding",
                change_type="open",
                item_key=need.get("need_key"),
                item_label=need_label,
                old_value=None,
                new_value="Open",
                detail=need_label,
                sort_order=sort_order,
                created_at=created_at,
            )
            sort_order += 1
    else:
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


def build_note_summary(
    case_manager_update_id: int,
    enrollment_id: int,
    resident_id: int,
    meeting_date: str | None,
    form,
    service_types: list[str],
    changed_needs: list[dict],
    created_at: str,
) -> None:
    previous_note_id = get_previous_note_id(
        enrollment_id=enrollment_id,
        current_note_id=case_manager_update_id,
        current_meeting_date=meeting_date,
    )

    previous_child_snapshot = load_previous_snapshot_map(previous_note_id, "child")
    previous_medication_snapshot = load_previous_snapshot_map(previous_note_id, "medication")
    previous_employment_snapshot = load_previous_snapshot_map(previous_note_id, "employment")
    previous_sobriety_snapshot = load_previous_snapshot_map(previous_note_id, "sobriety")
    previous_advancement_snapshot = load_previous_snapshot_map(previous_note_id, "advancement")

    current_child_snapshot = get_current_children_snapshot(resident_id)
    current_medication_snapshot = get_current_medication_snapshot(resident_id)
    current_employment_snapshot = get_current_employment_snapshot(resident_id)
    current_sobriety_snapshot = get_current_sobriety_snapshot(resident_id)
    current_advancement_snapshot = get_current_advancement_snapshot(enrollment_id)
    current_outstanding_needs = current_open_needs(enrollment_id)

    sort_order = 0

    sort_order = record_service_summary(
        case_manager_update_id=case_manager_update_id,
        service_types=service_types,
        form=form,
        created_at=created_at,
        starting_sort_order=sort_order,
    )

    sort_order = record_need_summary(
        case_manager_update_id=case_manager_update_id,
        changed_needs=changed_needs,
        outstanding_needs=current_outstanding_needs,
        created_at=created_at,
        starting_sort_order=sort_order,
    )

    sort_order = record_snapshot_change_group(
        case_manager_update_id=case_manager_update_id,
        change_group="child",
        previous_snapshot=previous_child_snapshot,
        current_snapshot=current_child_snapshot,
        label_map=None,
        added_label="Child Added",
        removed_label="Child Removed",
        updated_label="Child Updated",
        created_at=created_at,
        starting_sort_order=sort_order,
    )

    sort_order = record_snapshot_change_group(
        case_manager_update_id=case_manager_update_id,
        change_group="medication",
        previous_snapshot=previous_medication_snapshot,
        current_snapshot=current_medication_snapshot,
        label_map=None,
        added_label="Medication Added",
        removed_label="Medication Removed",
        updated_label="Medication Updated",
        created_at=created_at,
        starting_sort_order=sort_order,
    )

    sort_order = record_snapshot_change_group(
        case_manager_update_id=case_manager_update_id,
        change_group="employment",
        previous_snapshot=previous_employment_snapshot,
        current_snapshot=current_employment_snapshot,
        label_map=EMPLOYMENT_FIELD_LABELS,
        added_label="",
        removed_label="",
        updated_label="",
        created_at=created_at,
        starting_sort_order=sort_order,
    )

    sort_order = record_snapshot_change_group(
        case_manager_update_id=case_manager_update_id,
        change_group="sobriety",
        previous_snapshot=previous_sobriety_snapshot,
        current_snapshot=current_sobriety_snapshot,
        label_map=SOBRIETY_FIELD_LABELS,
        added_label="",
        removed_label="",
        updated_label="",
        created_at=created_at,
        starting_sort_order=sort_order,
    )

    record_snapshot_change_group(
        case_manager_update_id=case_manager_update_id,
        change_group="advancement",
        previous_snapshot=previous_advancement_snapshot,
        current_snapshot=current_advancement_snapshot,
        label_map={
            **MEETING_TEXT_FIELD_LABELS,
            **ADVANCEMENT_BOOL_FIELD_LABELS,
            **ADVANCEMENT_TEXT_FIELD_LABELS,
        },
        added_label="",
        removed_label="",
        updated_label="",
        created_at=created_at,
        starting_sort_order=sort_order,
    )
