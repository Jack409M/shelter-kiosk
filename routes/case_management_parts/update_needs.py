from __future__ import annotations

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.needs import normalize_need_status


ALLOWED_RESOLUTION_STATUSES = {"addressed", "not_applicable"}


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalized_resolution_note(form, need_key: str) -> str:
    return _clean_text(form.get(f"need_note_{need_key}"))


def _open_needs_for_enrollment(enrollment_id: int) -> list[dict]:
    ph = placeholder()

    return db_fetchall(
        f"""
        SELECT
            id,
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


def current_open_needs(enrollment_id: int) -> list[dict]:
    open_needs = _open_needs_for_enrollment(enrollment_id)

    return [
        {
            "need_key": row["need_key"],
            "need_label": row["need_label"],
            "resolution_note": row.get("resolution_note"),
        }
        for row in open_needs
    ]


def collect_need_updates(form) -> list[dict]:
    updates: list[dict] = []
    seen_need_keys: set[str] = set()

    for key in form.keys():
        if not key.startswith("need_status_"):
            continue

        need_key = key.removeprefix("need_status_").strip()
        if not need_key or need_key in seen_need_keys:
            continue

        status = normalize_need_status(form.get(key))
        if status not in ALLOWED_RESOLUTION_STATUSES:
            continue

        seen_need_keys.add(need_key)
        updates.append(
            {
                "need_key": need_key,
                "status": status,
                "resolution_note": _normalized_resolution_note(form, need_key),
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

    open_needs = _open_needs_for_enrollment(enrollment_id)
    open_needs_by_key = {
        row["need_key"]: row
        for row in open_needs
        if row.get("need_key")
    }

    changed_needs: list[dict] = []

    for update in need_updates:
        need_key = _clean_text(update.get("need_key"))
        status = _clean_text(update.get("status"))
        resolution_note = _clean_text(update.get("resolution_note"))

        if not need_key or status not in ALLOWED_RESOLUTION_STATUSES:
            continue

        need = open_needs_by_key.get(need_key)
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
                status,
                resolution_note or None,
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
                "status": status,
                "resolution_note": resolution_note,
            }
        )

    return changed_needs
