from __future__ import annotations

from datetime import UTC, datetime

from flask import flash, redirect, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from routes.admin_parts.helpers import require_admin_role
from routes.case_management_parts.helpers import placeholder

_ACTIVE_RESIDENT_SQL = """
COALESCE(LOWER(TRIM(CAST(is_active AS TEXT))), '') IN ('1', 'true', 't', 'yes')
"""


def _staff_user_id() -> int | None:
    raw_staff_user_id = session.get("staff_user_id")
    try:
        return int(raw_staff_user_id) if raw_staff_user_id not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _duplicate_group_keys() -> tuple[str, str] | None:
    first_name_key = (request.form.get("first_name_key") or "").strip().lower()
    last_name_key = (request.form.get("last_name_key") or "").strip().lower()

    if not first_name_key or not last_name_key:
        return None

    return first_name_key, last_name_key


def _primary_and_duplicate_ids(first_name_key: str, last_name_key: str) -> tuple[int | None, list[int]]:
    ph = placeholder()

    review = db_fetchone(
        f"""
        SELECT primary_resident_id
        FROM duplicate_name_reviews
        WHERE first_name_key = {ph}
          AND last_name_key = {ph}
          AND status = 'needs_merge_review'
        LIMIT 1
        """,
        (first_name_key, last_name_key),
    )

    primary_resident_id = (review or {}).get("primary_resident_id")

    if not primary_resident_id:
        return None, []

    duplicate_rows = db_fetchall(
        f"""
        SELECT id
        FROM residents
        WHERE {_ACTIVE_RESIDENT_SQL}
          AND LOWER(TRIM(first_name)) = {ph}
          AND LOWER(TRIM(last_name)) = {ph}
          AND id <> {ph}
        ORDER BY id
        """,
        (first_name_key, last_name_key, primary_resident_id),
    ) or []

    duplicate_ids = [int(row.get("id")) for row in duplicate_rows if row.get("id")]
    return int(primary_resident_id), duplicate_ids


def select_duplicate_primary_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    keys = _duplicate_group_keys()
    raw_primary_resident_id = (request.form.get("primary_resident_id") or "").strip()

    if not keys or not raw_primary_resident_id:
        flash("Invalid primary selection.", "error")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    first_name_key, last_name_key = keys

    try:
        primary_resident_id = int(raw_primary_resident_id)
    except (TypeError, ValueError):
        flash("Invalid resident selection.", "error")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    ph = placeholder()

    resident_match = db_fetchone(
        f"""
        SELECT id
        FROM residents
        WHERE id = {ph}
          AND LOWER(TRIM(first_name)) = {ph}
          AND LOWER(TRIM(last_name)) = {ph}
        LIMIT 1
        """,
        (primary_resident_id, first_name_key, last_name_key),
    )

    if not resident_match:
        flash("Selected resident does not match this duplicate group.", "error")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    existing_review = db_fetchone(
        f"""
        SELECT id
        FROM duplicate_name_reviews
        WHERE first_name_key = {ph}
          AND last_name_key = {ph}
          AND status = 'needs_merge_review'
        LIMIT 1
        """,
        (first_name_key, last_name_key),
    )

    if not existing_review:
        flash("Duplicate group is no longer in merge review.", "warning")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    now = datetime.now(UTC).replace(tzinfo=None).isoformat()

    with db_transaction():
        db_execute(
            f"""
            UPDATE duplicate_name_reviews
            SET primary_resident_id = {ph},
                primary_selected_by_user_id = {ph},
                primary_selected_at = {ph},
                updated_at = {ph}
            WHERE first_name_key = {ph}
              AND last_name_key = {ph}
              AND status = 'needs_merge_review'
            """,
            (
                primary_resident_id,
                _staff_user_id(),
                now,
                now,
                first_name_key,
                last_name_key,
            ),
        )

    flash("Primary resident selected.", "success")
    return redirect(url_for("admin.duplicate_merge_review_queue"))


def duplicate_merge_dry_run_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    keys = _duplicate_group_keys()

    if not keys:
        flash("Invalid merge dry run request.", "error")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    first_name_key, last_name_key = keys
    primary_resident_id, duplicate_ids = _primary_and_duplicate_ids(first_name_key, last_name_key)

    if not primary_resident_id:
        flash("Select a primary resident before running a merge dry run.", "warning")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    if not duplicate_ids:
        flash("Dry run complete: no duplicate records would be merged.", "info")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    flash(
        "Dry run only: would keep resident "
        f"{primary_resident_id} as PRIMARY and merge duplicate resident ID(s): "
        f"{', '.join(str(duplicate_id) for duplicate_id in duplicate_ids)}.",
        "info",
    )
    return redirect(url_for("admin.duplicate_merge_review_queue"))


def duplicate_merge_execute_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    keys = _duplicate_group_keys()

    if not keys:
        flash("Invalid merge request.", "error")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    first_name_key, last_name_key = keys
    primary_resident_id, duplicate_ids = _primary_and_duplicate_ids(first_name_key, last_name_key)

    if not primary_resident_id:
        flash("Select a primary resident before merging.", "warning")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    if not duplicate_ids:
        flash("No duplicate records to merge.", "info")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    ph = placeholder()
    now = datetime.now(UTC).replace(tzinfo=None).isoformat()

    with db_transaction():
        for duplicate_id in duplicate_ids:
            db_execute(
                f"""
                UPDATE resident_children
                SET resident_id = {ph}, updated_at = {ph}
                WHERE resident_id = {ph}
                """,
                (primary_resident_id, now, duplicate_id),
            )

            db_execute(
                f"""
                UPDATE resident_child_income_supports
                SET resident_id = {ph}, updated_at = {ph}
                WHERE resident_id = {ph}
                """,
                (primary_resident_id, now, duplicate_id),
            )

            db_execute(
                f"""
                UPDATE resident_passes
                SET status = 'expired', updated_at = {ph}
                WHERE resident_id = {ph}
                  AND status IN ('pending', 'approved')
                """,
                (now, duplicate_id),
            )

            db_execute(
                f"""
                UPDATE resident_passes
                SET resident_id = {ph}, updated_at = {ph}
                WHERE resident_id = {ph}
                """,
                (primary_resident_id, now, duplicate_id),
            )

            db_execute(
                f"""
                UPDATE resident_notifications
                SET resident_id = {ph}
                WHERE resident_id = {ph}
                """,
                (primary_resident_id, duplicate_id),
            )

            db_execute(
                f"""
                UPDATE residents
                SET is_active = {ph}, updated_at = {ph}
                WHERE id = {ph}
                """,
                (False, now, duplicate_id),
            )

        db_execute(
            f"""
            UPDATE duplicate_name_reviews
            SET status = 'merged', updated_at = {ph}
            WHERE first_name_key = {ph}
              AND last_name_key = {ph}
              AND status = 'needs_merge_review'
            """,
            (now, first_name_key, last_name_key),
        )

    flash(f"Merged {len(duplicate_ids)} duplicate record(s) into PRIMARY resident {primary_resident_id}.", "success")
    return redirect(url_for("admin.duplicate_merge_review_queue"))
