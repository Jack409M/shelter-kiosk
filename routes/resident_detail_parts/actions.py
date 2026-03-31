from __future__ import annotations

from flask import flash, redirect, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import resident_has_active_enrollment


def create_enrollment_view(
    resident_id: int,
    shelter: str,
    sql_selector,
    shelter_equals_sql,
    case_manager_allowed_fn,
):
    if not case_manager_allowed_fn():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    resident = db_fetchone(
        sql_selector(
            f"""
            SELECT
                id,
                shelter
            FROM residents
            WHERE id = %s AND {shelter_equals_sql("shelter")}
            """,
            f"""
            SELECT
                id,
                shelter
            FROM residents
            WHERE id = ? AND {shelter_equals_sql("shelter")}
            """,
        ),
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    if resident_has_active_enrollment(resident_id):
        flash("Resident already has an active enrollment.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    entry_date = (request.form.get("entry_date") or "").strip()

    if not entry_date:
        flash("Entry date required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    now = utcnow_iso()

    db_execute(
        sql_selector(
            """
            INSERT INTO program_enrollments
            (resident_id, shelter, entry_date, exit_date, program_status, case_manager_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            """
            INSERT INTO program_enrollments
            (resident_id, shelter, entry_date, exit_date, program_status, case_manager_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
        ),
        (
            resident_id,
            shelter,
            entry_date,
            None,
            "active",
            session.get("staff_user_id"),
            now,
            now,
        ),
    )

    flash("Program enrollment started.", "ok")
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id) + "#start-enrollment")


def add_goal_view(
    resident_id: int,
    shelter: str,
    sql_selector,
    shelter_equals_sql,
    case_manager_allowed_fn,
    load_enrollment_context_for_shelter_fn,
):
    if not case_manager_allowed_fn():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    context = load_enrollment_context_for_shelter_fn(
        resident_id,
        shelter,
        sql_selector,
        shelter_equals_sql,
    )
    resident = context["resident"]
    enrollment_id = context["enrollment_id"]

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    if not enrollment_id:
        flash("This resident does not have an active enrollment record yet.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    goal_text = (request.form.get("goal_text") or "").strip()
    target_date = (request.form.get("target_date") or "").strip()

    if not goal_text:
        flash("Goal text is required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    now = utcnow_iso()

    db_execute(
        sql_selector(
            """
            INSERT INTO goals
            (enrollment_id, goal_text, status, target_date, completed_date, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            """
            INSERT INTO goals
            (enrollment_id, goal_text, status, target_date, completed_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
        ),
        (
            enrollment_id,
            goal_text,
            "active",
            target_date or None,
            None,
            now,
            now,
        ),
    )

    flash("Goal added.", "ok")
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id) + "#add-goal")


def complete_goal_view(
    goal_id: int,
    shelter: str,
    sql_selector,
    shelter_equals_sql,
    case_manager_allowed_fn,
    row_value_fn,
):
    if not case_manager_allowed_fn():
        flash("Case manager access required.", "error")
        return redirect(url_for("residents.staff_residents"))

    goal = db_fetchone(
        sql_selector(
            f"""
            SELECT
                g.id,
                r.id AS resident_id
            FROM goals g
            JOIN program_enrollments pe
                ON pe.id = g.enrollment_id
            JOIN residents r
                ON r.id = pe.resident_id
            WHERE g.id = %s
              AND {shelter_equals_sql("r.shelter")}
            """,
            f"""
            SELECT
                g.id,
                r.id AS resident_id
            FROM goals g
            JOIN program_enrollments pe
                ON pe.id = g.enrollment_id
            JOIN residents r
                ON r.id = pe.resident_id
            WHERE g.id = ?
              AND {shelter_equals_sql("r.shelter")}
            """,
        ),
        (goal_id, shelter),
    )

    if not goal:
        flash("Goal not found or not accessible.", "error")
        return redirect(url_for("residents.staff_residents"))

    resident_id = row_value_fn(goal, "resident_id", 1)
    now = utcnow_iso()

    db_execute(
        sql_selector(
            """
            UPDATE goals
            SET status = %s,
                completed_date = %s,
                updated_at = %s
            WHERE id = %s
            """,
            """
            UPDATE goals
            SET status = ?,
                completed_date = ?,
                updated_at = ?
            WHERE id = ?
            """,
        ),
        (
            "completed",
            now,
            now,
            goal_id,
        ),
    )

    flash("Goal marked completed.", "ok")
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id) + "#goals")


def add_case_note_view(
    resident_id: int,
    shelter: str,
    sql_selector,
    shelter_equals_sql,
    case_manager_allowed_fn,
    load_enrollment_context_for_shelter_fn,
):
    staff_user_id = session.get("staff_user_id")

    if not case_manager_allowed_fn():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    context = load_enrollment_context_for_shelter_fn(
        resident_id,
        shelter,
        sql_selector,
        shelter_equals_sql,
    )
    resident = context["resident"]
    enrollment_id = context["enrollment_id"]

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    if not enrollment_id:
        flash("Resident does not have an active enrollment record yet.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    if not staff_user_id:
        flash("Your session is missing a staff user id. Please log in again.", "error")
        return redirect(url_for("auth.staff_login"))

    meeting_date = (request.form.get("meeting_date") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    progress_notes = (request.form.get("progress_notes") or "").strip()
    action_items = (request.form.get("action_items") or "").strip()

    if not meeting_date and not notes and not progress_notes and not action_items:
        flash("Enter at least one case manager note field.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    now = utcnow_iso()

    db_execute(
        sql_selector(
            """
            INSERT INTO case_manager_updates
            (enrollment_id, staff_user_id, meeting_date, notes, progress_notes, action_items, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            """
            INSERT INTO case_manager_updates
            (enrollment_id, staff_user_id, meeting_date, notes, progress_notes, action_items, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
        ),
        (
            enrollment_id,
            staff_user_id,
            meeting_date or None,
            notes or None,
            progress_notes or None,
            action_items or None,
            now,
            now,
        ),
    )

    flash("Case manager note added.", "ok")
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id) + "#add-case-note")


def add_appointment_view(
    resident_id: int,
    shelter: str,
    sql_selector,
    shelter_equals_sql,
    case_manager_allowed_fn,
    load_enrollment_context_for_shelter_fn,
):
    if not case_manager_allowed_fn():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    context = load_enrollment_context_for_shelter_fn(
        resident_id,
        shelter,
        sql_selector,
        shelter_equals_sql,
    )
    resident = context["resident"]
    enrollment_id = context["enrollment_id"]

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    if not enrollment_id:
        flash("Resident does not have an active enrollment record yet.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    appointment_date = (request.form.get("appointment_date") or "").strip()
    appointment_type = (request.form.get("appointment_type") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    if not appointment_date:
        flash("Appointment date is required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    now = utcnow_iso()

    db_execute(
        sql_selector(
            """
            INSERT INTO appointments
            (enrollment_id, appointment_type, appointment_date, notes, reminder_sent, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            """
            INSERT INTO appointments
            (enrollment_id, appointment_type, appointment_date, notes, reminder_sent, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
        ),
        (
            enrollment_id,
            appointment_type or None,
            appointment_date,
            notes or None,
            0,
            now,
            now,
        ),
    )

    flash("Appointment scheduled.", "ok")
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id) + "#add-appointment")
