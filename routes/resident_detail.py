from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import case_manager_allowed as _shared_case_manager_allowed
from routes.case_management_parts.helpers import resident_has_active_enrollment
from routes.case_management_parts.helpers import normalize_shelter_name as _shared_normalize_shelter_name
from routes.case_management_parts.helpers import shelter_equals_sql as _shared_shelter_equals_sql
from routes.resident_detail_parts.read import load_enrollment_context_for_shelter
from routes.resident_detail_parts.read import load_resident_for_shelter
from routes.resident_detail_parts.read import row_value
from routes.resident_detail_parts.timeline import build_calendar_context
from routes.resident_detail_parts.timeline import coerce_calendar_view
from routes.resident_detail_parts.timeline import normalize_timeline
from routes.resident_detail_parts.timeline import load_timeline
from routes.resident_detail_parts.timeline import parse_anchor_date
from routes.resident_detail_parts.timeline import parse_dt

resident_detail = Blueprint(
    "resident_detail",
    __name__,
    url_prefix="/staff/resident",
)


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _normalize_shelter_name(value: str | None) -> str:
    return _shared_normalize_shelter_name(value)


def _shelter_equals_sql(column_name: str) -> str:
    return _shared_shelter_equals_sql(column_name)


def _case_manager_allowed() -> bool:
    return _shared_case_manager_allowed()


def _resident_detail_view_allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager", "ra", "staff"}


def _days_in_program(entry_date_value) -> str:
    entry_dt = parse_dt(entry_date_value)
    if not entry_dt:
        return "—"

    days = (datetime.utcnow().date() - entry_dt.date()).days
    if days < 0:
        days = 0
    return str(days)


def _days_sober_today(sobriety_date_value):
    sobriety_dt = parse_dt(sobriety_date_value)
    if not sobriety_dt:
        return None

    days = (datetime.utcnow().date() - sobriety_dt.date()).days
    if days < 0:
        days = 0
    return days


@resident_detail.route("/<int:resident_id>")
@require_login
@require_shelter
def resident_profile(resident_id: int):
    if not _resident_detail_view_allowed():
        flash("Resident detail access required.", "error")
        return redirect(url_for("residents.staff_residents"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    resident = load_resident_for_shelter(
        resident_id,
        shelter,
        _sql,
        _shelter_equals_sql,
    )

    if not resident:
        return render_template(
            "resident_detail/profile.html",
            resident=None,
            compliance=None,
            goals=[],
            notes=[],
            appointment=None,
            snapshot=None,
            days_sober_today=None,
        )

    days_sober_today = _days_sober_today(row_value(resident, "sobriety_date", 19))

    return render_template(
        "resident_detail/profile.html",
        resident=resident,
        compliance=None,
        goals=[],
        notes=[],
        appointment=None,
        snapshot=None,
        days_sober_today=days_sober_today,
    )


@resident_detail.route("/<int:resident_id>/timeline")
@require_login
@require_shelter
def resident_timeline(resident_id: int):
    if not _resident_detail_view_allowed():
        flash("Resident detail access required.", "error")
        return redirect(url_for("residents.staff_residents"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    resident = load_resident_for_shelter(
        resident_id,
        shelter,
        _sql,
        _shelter_equals_sql,
    )

    selected_view = coerce_calendar_view(request.args.get("view"))
    anchor_date = parse_anchor_date(request.args.get("anchor"))
    empty_calendar = build_calendar_context([], selected_view, anchor_date)

    if not resident:
        return render_template(
            "resident_detail/timeline.html",
            resident=None,
            timeline=[],
            snapshot=None,
            calendar=empty_calendar,
        )

    enrollment_id = row_value(resident, "enrollment_id", 5)

    timeline = []
    snapshot = None
    calendar = empty_calendar

    if enrollment_id:
        timeline = normalize_timeline(load_timeline(enrollment_id, _sql))
        snapshot = {
            "program_status": str(row_value(resident, "program_status", 7, "—") or "—").replace("_", " ").title(),
            "days_in_program": _days_in_program(row_value(resident, "entry_date", 8)),
        }
        calendar = build_calendar_context(timeline, selected_view, anchor_date)

    return render_template(
        "resident_detail/timeline.html",
        resident=resident,
        timeline=timeline,
        snapshot=snapshot,
        calendar=calendar,
    )


@resident_detail.post("/<int:resident_id>/enroll")
@require_login
@require_shelter
def create_enrollment(resident_id: int):
    shelter = _normalize_shelter_name(session.get("shelter"))

    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    from core.db import db_fetchone

    resident = db_fetchone(
        _sql(
            f"""
            SELECT
                id,
                shelter
            FROM residents
            WHERE id = %s AND {_shelter_equals_sql("shelter")}
            """,
            f"""
            SELECT
                id,
                shelter
            FROM residents
            WHERE id = ? AND {_shelter_equals_sql("shelter")}
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
        _sql(
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


@resident_detail.post("/<int:resident_id>/goals")
@require_login
@require_shelter
def add_goal(resident_id: int):
    shelter = _normalize_shelter_name(session.get("shelter"))

    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    context = load_enrollment_context_for_shelter(
        resident_id,
        shelter,
        _sql,
        _shelter_equals_sql,
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
        _sql(
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


@resident_detail.post("/goal/<int:goal_id>/complete")
@require_login
@require_shelter
def complete_goal(goal_id: int):
    shelter = _normalize_shelter_name(session.get("shelter"))

    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("residents.staff_residents"))

    from core.db import db_fetchone

    goal = db_fetchone(
        _sql(
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
              AND {_shelter_equals_sql("r.shelter")}
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
              AND {_shelter_equals_sql("r.shelter")}
            """,
        ),
        (goal_id, shelter),
    )

    if not goal:
        flash("Goal not found or not accessible.", "error")
        return redirect(url_for("residents.staff_residents"))

    resident_id = row_value(goal, "resident_id", 1)
    now = utcnow_iso()

    db_execute(
        _sql(
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


@resident_detail.post("/<int:resident_id>/case-note")
@require_login
@require_shelter
def add_case_note(resident_id: int):
    shelter = _normalize_shelter_name(session.get("shelter"))
    staff_user_id = session.get("staff_user_id")

    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    context = load_enrollment_context_for_shelter(
        resident_id,
        shelter,
        _sql,
        _shelter_equals_sql,
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
        _sql(
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


@resident_detail.post("/<int:resident_id>/appointments")
@require_login
@require_shelter
def add_appointment(resident_id: int):
    shelter = _normalize_shelter_name(session.get("shelter"))

    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    context = load_enrollment_context_for_shelter(
        resident_id,
        shelter,
        _sql,
        _shelter_equals_sql,
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
        _sql(
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
