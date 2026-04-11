from __future__ import annotations

from core.db import db_fetchall
from core.db import db_fetchone
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.resident_case_notes import build_note_objects


def load_single_case_note(enrollment_id: int, update_id: int):
    ph = placeholder()

    notes_raw = db_fetchall(
        f"""
        SELECT
            id,
            staff_user_id,
            meeting_date,
            notes,
            progress_notes,
            setbacks_or_incidents,
            action_items,
            next_appointment,
            overall_summary,
            ready_for_next_level,
            recommended_next_level,
            blocker_reason,
            override_or_exception,
            staff_review_note,
            updated_grit,
            parenting_class_completed,
            warrants_or_fines_paid,
            created_at
        FROM case_manager_updates
        WHERE enrollment_id = {ph}
          AND id = {ph}
        LIMIT 1
        """,
        (enrollment_id, update_id),
    )

    if not notes_raw:
        return None

    services_raw = db_fetchall(
        f"""
        SELECT
            case_manager_update_id,
            service_type,
            service_date,
            quantity,
            unit,
            notes
        FROM client_services
        WHERE enrollment_id = {ph}
          AND case_manager_update_id = {ph}
        ORDER BY service_date DESC, id DESC
        """,
        (enrollment_id, update_id),
    )

    summary_rows_raw = db_fetchall(
        f"""
        SELECT
            case_manager_update_id,
            change_group,
            change_type,
            item_key,
            item_label,
            old_value,
            new_value,
            detail,
            sort_order
        FROM case_manager_update_summary
        WHERE case_manager_update_id = {ph}
        ORDER BY sort_order ASC, id ASC
        """,
        (update_id,),
    )

    notes, _ = build_note_objects(notes_raw, services_raw, summary_rows_raw)
    return notes[0] if notes else None


def load_goals(enrollment_id: int) -> list[dict]:
    ph = placeholder()

    return db_fetchall(
        f"""
        SELECT
            goal_text,
            status,
            target_date
        FROM goals
        WHERE enrollment_id = {ph}
        ORDER BY created_at DESC, id DESC
        """,
        (enrollment_id,),
    )


def load_case_manager_name(staff_user_id: int | None) -> str:
    if not staff_user_id:
        return "Current Staff"

    ph = placeholder()
    row = db_fetchone(
        f"""
        SELECT
            first_name,
            last_name,
            username
        FROM staff_users
        WHERE id = {ph}
        LIMIT 1
        """,
        (staff_user_id,),
    )

    if not row:
        return "Current Staff"

    first_name = (row.get("first_name") or "").strip()
    last_name = (row.get("last_name") or "").strip()
    username = (row.get("username") or "").strip()

    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    return full_name or username or "Current Staff"
