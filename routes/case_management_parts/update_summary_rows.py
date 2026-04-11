from __future__ import annotations

from core.db import db_execute
from core.db import db_fetchone
from routes.case_management_parts.helpers import placeholder


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
