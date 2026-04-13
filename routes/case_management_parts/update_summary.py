from __future__ import annotations

from core.db import db_fetchone
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.update_needs import current_open_needs
from routes.case_management_parts.update_snapshots import (
    get_current_advancement_snapshot,
    get_current_children_snapshot,
    get_current_employment_snapshot,
    get_current_medication_snapshot,
    get_current_sobriety_snapshot,
    load_previous_snapshot_map,
)
from routes.case_management_parts.update_summary_recorders import (
    record_need_summary,
    record_service_summary,
    record_snapshot_change_group,
)
from routes.case_management_parts.update_utils import (
    ADVANCEMENT_BOOL_FIELD_LABELS,
    ADVANCEMENT_TEXT_FIELD_LABELS,
    EMPLOYMENT_FIELD_LABELS,
    MEETING_TEXT_FIELD_LABELS,
    SOBRIETY_FIELD_LABELS,
)


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
