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


def _duplicate_keys_from_request() -> tuple[str, str] | None:
    first_name_key = (request.form.get("first_name_key") or "").strip().lower()
    last_name_key = (request.form.get("last_name_key") or "").strip().lower()

    if not first_name_key or not last_name_key:
        return None

    return first_name_key, last_name_key


def _active_match_count(first_name_key: str, last_name_key: str) -> int:
    ph = placeholder()
    row = db_fetchone(
        f"""
        SELECT COUNT(*) AS count
        FROM residents
        WHERE {_ACTIVE_RESIDENT_SQL}
          AND LOWER(TRIM(first_name)) = {ph}
          AND LOWER(TRIM(last_name)) = {ph}
        """,
        (first_name_key, last_name_key),
    ) or {}

    try:
        return int(row.get("count") or 0)
    except (TypeError, ValueError):
        return 0


def mark_duplicate_names_same_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    keys = _duplicate_keys_from_request()
    if not keys:
        flash("Invalid duplicate review request.", "error")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    first_name_key, last_name_key = keys
    ph = placeholder()

    if _active_match_count(first_name_key, last_name_key) < 2:
        flash("Duplicate group no longer has multiple active matching residents.", "warning")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    existing = db_fetchone(
        f"""
        SELECT id
        FROM duplicate_name_reviews
        WHERE first_name_key = {ph}
          AND last_name_key = {ph}
          AND status = {ph}
        LIMIT 1
        """,
        (first_name_key, last_name_key, "needs_merge_review"),
    )

    if existing:
        flash("Duplicate group is already in merge review.", "info")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    now = datetime.now(UTC).replace(tzinfo=None).isoformat()

    with db_transaction():
        db_execute(
            f"""
            INSERT INTO duplicate_name_reviews
            (
                first_name_key,
                last_name_key,
                status,
                reviewed_by_user_id,
                reviewed_at,
                created_at,
                updated_at
            )
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """,
            (
                first_name_key,
                last_name_key,
                "needs_merge_review",
                _staff_user_id(),
                now,
                now,
                now,
            ),
        )

    flash("Duplicate group marked as same person and added to merge review.", "warning")
    return redirect(url_for("admin.duplicate_merge_review_queue"))


def _resident_summary_rows(first_name_key: str, last_name_key: str) -> list[dict]:
    ph = placeholder()
    return db_fetchall(
        f"""
        SELECT
            r.id,
            r.resident_identifier,
            r.first_name,
            r.last_name,
            r.birth_year,
            r.phone,
            r.email,
            r.shelter,
            r.is_active,
            pe.id AS enrollment_id,
            pe.shelter AS enrollment_shelter,
            pe.entry_date,
            pe.program_status,
            CASE WHEN ia.id IS NULL THEN 0 ELSE 1 END AS intake_exists,
            COALESCE(children.child_count, 0) AS child_count,
            COALESCE(notes.note_count, 0) AS note_count,
            COALESCE(passes.pass_count, 0) AS pass_count
        FROM residents r
        LEFT JOIN program_enrollments pe
          ON pe.resident_id = r.id
         AND LOWER(TRIM(COALESCE(pe.program_status, ''))) = 'active'
        LEFT JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        LEFT JOIN (
            SELECT resident_id, COUNT(*) AS child_count
            FROM resident_children
            GROUP BY resident_id
        ) children ON children.resident_id = r.id
        LEFT JOIN (
            SELECT resident_id, COUNT(*) AS note_count
            FROM case_notes
            GROUP BY resident_id
        ) notes ON notes.resident_id = r.id
        LEFT JOIN (
            SELECT resident_id, COUNT(*) AS pass_count
            FROM resident_passes
            GROUP BY resident_id
        ) passes ON passes.resident_id = r.id
        WHERE {_ACTIVE_RESIDENT_SQL.replace('is_active', 'r.is_active')}
          AND LOWER(TRIM(r.first_name)) = {ph}
          AND LOWER(TRIM(r.last_name)) = {ph}
        ORDER BY r.id
        """,
        (first_name_key, last_name_key),
    ) or []


def duplicate_merge_review_queue_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    groups = db_fetchall(
        """
        SELECT
            first_name_key,
            last_name_key,
            MIN(reviewed_at) AS reviewed_at,
            COUNT(*) AS review_count
        FROM duplicate_name_reviews
        WHERE status = 'needs_merge_review'
        GROUP BY first_name_key, last_name_key
        ORDER BY MIN(reviewed_at) DESC, last_name_key, first_name_key
        """
    ) or []

    queue = []

    for group in groups:
        first_name_key = group["first_name_key"]
        last_name_key = group["last_name_key"]
        residents = _resident_summary_rows(first_name_key, last_name_key)

        queue.append(
            {
                "first_name_key": first_name_key,
                "last_name_key": last_name_key,
                "reviewed_at": group.get("reviewed_at"),
                "review_count": group.get("review_count"),
                "residents": residents,
            }
        )

    return render_template(
        "duplicate_merge_review_queue.html",
        title="Duplicate Merge Review Queue",
        queue=queue,
    )


def duplicate_merge_resident_snapshot_view(resident_id: int):
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    ph = placeholder()
    resident = db_fetchone(
        f"""
        SELECT
            r.*,
            pe.id AS enrollment_id,
            pe.shelter AS enrollment_shelter,
            pe.entry_date,
            pe.program_status,
            CASE WHEN ia.id IS NULL THEN 0 ELSE 1 END AS intake_exists,
            COALESCE(children.child_count, 0) AS child_count,
            COALESCE(notes.note_count, 0) AS note_count,
            COALESCE(passes.pass_count, 0) AS pass_count
        FROM residents r
        LEFT JOIN program_enrollments pe
          ON pe.resident_id = r.id
         AND LOWER(TRIM(COALESCE(pe.program_status, ''))) = 'active'
        LEFT JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        LEFT JOIN (
            SELECT resident_id, COUNT(*) AS child_count
            FROM resident_children
            GROUP BY resident_id
        ) children ON children.resident_id = r.id
        LEFT JOIN (
            SELECT resident_id, COUNT(*) AS note_count
            FROM case_notes
            GROUP BY resident_id
        ) notes ON notes.resident_id = r.id
        LEFT JOIN (
            SELECT resident_id, COUNT(*) AS pass_count
            FROM resident_passes
            GROUP BY resident_id
        ) passes ON passes.resident_id = r.id
        WHERE r.id = {ph}
        LIMIT 1
        """,
        (resident_id,),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("admin.duplicate_merge_review_queue"))

    return render_template(
        "duplicate_merge_resident_snapshot.html",
        title="Resident Merge Snapshot",
        resident=resident,
    )
