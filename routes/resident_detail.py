from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import case_manager_allowed as _shared_case_manager_allowed
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name as _shared_normalize_shelter_name
from routes.case_management_parts.helpers import resident_has_active_enrollment
from routes.case_management_parts.helpers import shelter_equals_sql as _shared_shelter_equals_sql
from routes.resident_detail_parts.timeline import build_calendar_context
from routes.resident_detail_parts.timeline import coerce_calendar_view
from routes.resident_detail_parts.timeline import format_dt
from routes.resident_detail_parts.timeline import format_time_only
from routes.resident_detail_parts.timeline import load_timeline
from routes.resident_detail_parts.timeline import normalize_timeline
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


def _row_value(row, key: str, index: int | None = None, default=None):
    if row is None:
        return default

    if isinstance(row, dict):
        value = row.get(key, default)
        return default if value is None else value

    try:
        value = row[key]
        return default if value is None else value
    except Exception:
        pass

    if index is not None:
        try:
            value = row[index]
            return default if value is None else value
        except Exception:
            pass

    return default


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


def _compliance_snapshot_text(compliance) -> str:
    submitted_at = _row_value(compliance, "submitted_at", 3)

    if not submitted_at:
        return "Not submitted"

    submitted_dt = parse_dt(submitted_at)
    if not submitted_dt:
        return "Submitted"

    if (datetime.utcnow().date() - submitted_dt.date()).days <= 7:
        return f"Submitted {format_dt(submitted_at, prefer_date_only=True)}"

    return "Not submitted this week"


def _load_resident_for_shelter(resident_id: int, shelter: str):
    resident = db_fetchone(
        _sql(
            f"""
            SELECT
                id,
                first_name,
                last_name,
                shelter AS resident_shelter,
                is_active,
                resident_code,
                birth_year,
                phone,
                email,
                emergency_contact_name,
                emergency_contact_relationship,
                emergency_contact_phone,
                medical_alerts,
                medical_notes
            FROM residents
            WHERE id = %s
              AND {_shelter_equals_sql("shelter")}
            LIMIT 1
            """,
            f"""
            SELECT
                id,
                first_name,
                last_name,
                shelter AS resident_shelter,
                is_active,
                resident_code,
                birth_year,
                phone,
                email,
                emergency_contact_name,
                emergency_contact_relationship,
                emergency_contact_phone,
                medical_alerts,
                medical_notes
            FROM residents
            WHERE id = ?
              AND {_shelter_equals_sql("shelter")}
            LIMIT 1
            """,
        ),
        (resident_id, shelter),
    )

    if not resident:
        return None

    enrollment = fetch_current_enrollment_for_resident(
        resident_id,
        columns="""
            id AS enrollment_id,
            shelter AS enrollment_shelter,
            program_status,
            entry_date,
            exit_date,
            (
                SELECT ia.sobriety_date
                FROM intake_assessments ia
                WHERE ia.enrollment_id = program_enrollments.id
                ORDER BY id DESC
                LIMIT 1
            ) AS sobriety_date,
            (
                SELECT ia.days_sober_at_entry
                FROM intake_assessments ia
                WHERE ia.enrollment_id = program_enrollments.id
                ORDER BY id DESC
                LIMIT 1
            ) AS days_sober_at_entry
        """,
    )

    merged = dict(resident)
    if enrollment:
        merged.update(dict(enrollment))
    else:
        merged.update(
            {
                "enrollment_id": None,
                "enrollment_shelter": None,
                "program_status": None,
                "entry_date": None,
                "exit_date": None,
                "sobriety_date": None,
                "days_sober_at_entry": None,
            }
        )

    return merged


def _next_appointment_for_enrollment(enrollment_id: int):
    today_iso = datetime.utcnow().date().isoformat()

    row = db_fetchone(
        _sql(
            """
            SELECT
                appointment_date,
                appointment_type,
                notes,
                reminder_sent,
                created_at
            FROM appointments
            WHERE enrollment_id = %s
              AND appointment_date IS NOT NULL
              AND appointment_date >= %s
            ORDER BY
                appointment_date ASC,
                id ASC
            LIMIT 1
            """,
            """
            SELECT
                appointment_date,
                appointment_type,
                notes,
                reminder_sent,
                created_at
            FROM appointments
            WHERE enrollment_id = ?
              AND appointment_date IS NOT NULL
              AND appointment_date >= ?
            ORDER BY
                appointment_date ASC,
                id ASC
            LIMIT 1
            """,
        ),
        (enrollment_id, today_iso),
    )

    if row:
        return row

    return db_fetchone(
        _sql(
            """
            SELECT
                appointment_date,
                appointment_type,
                notes,
                reminder_sent,
                created_at
            FROM appointments
            WHERE enrollment_id = %s
              AND appointment_date IS NOT NULL
            ORDER BY
                appointment_date DESC,
                id DESC
            LIMIT 1
            """,
            """
            SELECT
                appointment_date,
                appointment_type,
                notes,
                reminder_sent,
                created_at
            FROM appointments
            WHERE enrollment_id = ?
              AND appointment_date IS NOT NULL
            ORDER BY
                appointment_date DESC,
                id DESC
            LIMIT 1
            """,
        ),
        (enrollment_id,),
    )


def _resident_enrollment_for_shelter(resident_id: int, shelter: str):
    resident = db_fetchone(
        _sql(
            f"""
            SELECT
                id
            FROM residents
            WHERE id = %s
              AND {_shelter_equals_sql("shelter")}
            LIMIT 1
            """,
            f"""
            SELECT
                id
            FROM residents
            WHERE id = ?
              AND {_shelter_equals_sql("shelter")}
            LIMIT 1
            """,
        ),
        (resident_id, shelter),
    )

    if not resident:
        return None

    enrollment = fetch_current_enrollment_for_resident(
        resident_id,
        columns="id AS enrollment_id",
    )

    merged = dict(resident)
    merged["enrollment_id"] = _row_value(enrollment, "enrollment_id", 0)
    return merged


def _load_enrollment_context_for_shelter(resident_id: int, shelter: str) -> dict[str, object]:
    resident = _resident_enrollment_for_shelter(resident_id, shelter)
    enrollment_id = _row_value(resident, "enrollment_id", 1) if resident else None

    return {
        "resident": resident,
        "enrollment_id": enrollment_id,
    }


def _build_snapshot(resident, goals, compliance, appointment):
    program_status = _row_value(resident, "program_status", 7, "—") or "—"
    entry_date = _row_value(resident, "entry_date", 8)

    active_goal_count = 0
    for goal in goals or []:
        status = str(_row_value(goal, "status", 2, "") or "").strip().lower()
        if status != "completed":
            active_goal_count += 1

    appointment_date = _row_value(appointment, "appointment_date", 0)
    if appointment_date:
        next_appointment = format_dt(appointment_date)
    else:
        next_appointment = "None scheduled"

    return {
        "program_status": str(program_status).replace("_", " ").title(),
        "goal_count": str(active_goal_count),
        "next_appointment": next_appointment,
        "compliance_status": _compliance_snapshot_text(compliance),
        "days_in_program": _days_in_program(entry_date),
    }


@resident_detail.route("/<int:resident_id>")
@require_login
@require_shelter
def resident_profile(resident_id: int):
    if not _resident_detail_view_allowed():
        flash("Resident detail access required.", "error")
        return redirect(url_for("residents.staff_residents"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    resident = _load_resident_for_shelter(resident_id, shelter)

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

    days_sober_today = _days_sober_today(_row_value(resident, "sobriety_date", 19))

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
    resident = _load_resident_for_shelter(resident_id, shelter)

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

    enrollment_id = _row_value(resident, "enrollment_id", 5)

    timeline = []
    snapshot = None
    calendar = empty_calendar

    if enrollment_id:
        timeline = normalize_timeline(load_timeline(enrollment_id, _sql))
        snapshot = {
            "program_status": str(_row_value(resident, "program_status", 7, "—") or "—").replace("_", " ").title(),
            "days_in_program": _days_in_program(_row_value(resident, "entry_date", 8)),
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

    context = _load_enrollment_context_for_shelter(resident_id, shelter)
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

    resident_id = _row_value(goal, "resident_id", 1)
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

    context = _load_enrollment_context_for_shelter(resident_id, shelter)
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

    context = _load_enrollment_context_for_shelter(resident_id, shelter)
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
