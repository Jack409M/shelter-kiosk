from __future__ import annotations

from flask import flash, redirect, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql


def add_case_note_view(resident_id: int):
    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    staff_user_id = session.get("staff_user_id")
    ph = placeholder()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident = db_fetchone(
        f"""
        SELECT
            id,
            resident_identifier
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = db_fetchone(
        f"""
        SELECT
            id
        FROM program_enrollments
        WHERE resident_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    enrollment_id = None
    if enrollment:
        enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]

    if not enrollment_id:
        flash("Resident does not have an active enrollment record yet.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if not staff_user_id:
        flash("Your session is missing a staff user id. Please log in again.", "error")
        return redirect(url_for("auth.staff_login"))

    meeting_date = (request.form.get("meeting_date") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    progress_notes = (request.form.get("progress_notes") or "").strip()
    action_items = (request.form.get("action_items") or "").strip()

    if not meeting_date:
        flash("Meeting date is required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if not notes and not progress_notes and not action_items:
        flash("Enter notes, progress notes, or action items.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    now = utcnow_iso()

    db_execute(
        f"""
        INSERT INTO case_manager_updates
        (
            enrollment_id,
            staff_user_id,
            meeting_date,
            notes,
            progress_notes,
            action_items,
            created_at,
            updated_at
        )
        VALUES (
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph}
        )
        """,
        (
            enrollment_id,
            staff_user_id,
            meeting_date,
            notes or None,
            progress_notes or None,
            action_items or None,
            now,
            now,
        ),
    )

    flash("Case manager note added.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
