from __future__ import annotations

from datetime import UTC, datetime

from flask import flash, redirect, render_template, request, session, url_for

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


def select_duplicate_primary_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    first_name_key = (request.form.get("first_name_key") or "").strip().lower()
    last_name_key = (request.form.get("last_name_key") or "").strip().lower()
    primary_resident_id = request.form.get("primary_resident_id")

    if not first_name_key or not last_name_key or not primary_resident_id:
        flash("Invalid primary selection.", "error")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    try:
        primary_resident_id = int(primary_resident_id)
    except Exception:
        flash("Invalid resident selection.", "error")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    ph = placeholder()

    exists = db_fetchone(
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

    now = datetime.now(UTC).replace(tzinfo=None).isoformat()

    with db_transaction():
        if exists:
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
        else:
            db_execute(
                f"""
                INSERT INTO duplicate_name_reviews (
                    first_name_key,
                    last_name_key,
                    status,
                    primary_resident_id,
                    primary_selected_by_user_id,
                    primary_selected_at,
                    created_at,
                    updated_at
                ) VALUES ({ph},{ph},'needs_merge_review',{ph},{ph},{ph},{ph},{ph})
                """,
                (
                    first_name_key,
                    last_name_key,
                    primary_resident_id,
                    _staff_user_id(),
                    now,
                    now,
                    now,
                ),
            )

    flash("Primary resident selected.", "success")
    return redirect(url_for("admin.duplicate_merge_review_queue"))
