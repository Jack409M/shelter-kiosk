from __future__ import annotations

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.needs import normalize_need_status


def current_open_needs(enrollment_id: int) -> list[dict]:
    ph = placeholder()

    return db_fetchall(
        f"""
        SELECT
            need_key,
            need_label,
            resolution_note
        FROM resident_needs
        WHERE enrollment_id = {ph}
          AND status = 'open'
        ORDER BY need_label ASC, id ASC
        """,
        (enrollment_id,),
    )


def collect_need_updates(form) -> list[dict]:
    updates: list[dict] = []

    for key in form.keys():
        if not key.startswith("need_status_"):
            continue

        need_key = key.removeprefix("need_status_")
        status = normalize_need_status(form.get(key))
        if status not in {"addressed", "not_applicable"}:
            continue

        resolution_note = (form.get(f"need_note_{need_key}") or "").strip()

        updates.append(
            {
                "need_key": need_key,
                "status": status,
                "resolution_note": resolution_note,
            }
        )

    return updates


def apply_need_updates(
    enrollment_id: int,
    staff_user_id: int,
    need_updates: list[dict],
) -> list[dict]:
    if not need_updates:
        return []

    ph = placeholder()
    now = utcnow_iso()

    open_needs = db_fetchall(
        f"""
        SELECT
            id,
            need_key,
            need_label
        FROM resident_needs
        WHERE enrollment_id = {ph}
          AND status = 'open'
        ORDER BY need_label ASC, id ASC
        """,
        (enrollment_id,),
    )

    open_needs_by_key = {row["need_key"]: row for row in open_needs}
    changed_needs: list[dict] = []

    for update in need_updates:
        need = open_needs_by_key.get(update["need_key"])
        if not need:
            continue

        db_execute(
            f"""
            UPDATE resident_needs
            SET
                status = {ph},
                resolution_note = {ph},
                resolved_at = {ph},
                resolved_by_staff_user_id = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                update["status"],
                update["resolution_note"] or None,
                now,
                staff_user_id,
                now,
                need["id"],
            ),
        )

        changed_needs.append(
            {
                "need_key": need["need_key"],
                "need_label": need["need_label"],
                "status": update["status"],
                "resolution_note": update["resolution_note"],
            }
        )

    return changed_needs
