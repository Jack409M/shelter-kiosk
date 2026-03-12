from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

resident_detail = Blueprint(
    "resident_detail",
    __name__,
    url_prefix="/staff/resident",
)


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _case_manager_allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _resident_enrollment_for_shelter(resident_id: int, shelter: str):
    return db_fetchone(
        _sql(
            """
            SELECT
                r.id,
                pe.id AS enrollment_id
            FROM residents r
            LEFT JOIN program_enrollments pe
                ON pe.resident_id = r.id
            WHERE r.id = %s AND r.shelter = %s
            ORDER BY pe.id DESC
            LIMIT 1
            """,
            """
            SELECT
                r.id,
                pe.id AS enrollment_id
            FROM residents r
            LEFT JOIN program_enrollments pe
                ON pe.resident_id = r.id
            WHERE r.id = ? AND r.shelter = ?
            ORDER BY pe.id DESC
            LIMIT 1
            """,
        ),
        (resident_id, shelter),
    )


def _load_timeline(enrollment_id: int):
    return db_fetchall(
        _sql(
            """
            SELECT
                event_time,
                event_type,
                title,
                detail,
                sort_order
            FROM (
                SELECT
                    pe.created_at AS event_time,
                    'enrollment_started' AS event_type,
                    'Program enrollment started' AS title,
                    CONCAT('Status: ', COALESCE(pe.program_status, 'active')) AS detail,
                    1 AS sort_order
                FROM program_enrollments pe
                WHERE pe.id = %s

                UNION ALL

                SELECT
                    g.created_at AS event_time,
                    'goal_created' AS event_type,
                    'Goal created' AS title,
                    g.goal_text AS detail,
                    2 AS sort_order
                FROM goals g
                WHERE g.enrollment_id = %s

                UNION ALL

                SELECT
                    g.completed_date AS event_time,
                    'goal_completed' AS event_type,
                    'Goal completed' AS title,
                    g.goal_text AS detail,
                    3 AS sort_order
                FROM goals g
                WHERE g.enrollment_id = %s
                  AND g.completed_date IS NOT NULL

                UNION ALL

                SELECT
                    COALESCE(cmu.meeting_date, cmu.created_at) AS event_time,
                    'case_note' AS event_type,
                    'Case manager note' AS title,
                    COALESCE(cmu.notes, cmu.progress_notes, cmu.action_items, 'Case update recorded') AS detail,
                    4 AS sort_order
                FROM case_manager_updates cmu
                WHERE cmu.enrollment_id = %s

                UNION ALL

                SELECT
                    wrs.submitted_at AS event_time,
                    'compliance_submitted' AS event_type,
                    'Weekly compliance submitted' AS title,
                    CONCAT(
                        'Productive Hours: ', COALESCE(wrs.productive_hours::text, '0'),
                        ' | Work Hours: ', COALESCE(wrs.work_hours::text, '0'),
                        ' | Meetings: ', COALESCE(wrs.meeting_count::text, '0')
                    ) AS detail,
                    5 AS sort_order
                FROM weekly_resident_summary wrs
                WHERE wrs.enrollment_id = %s

                UNION ALL

                SELECT
                    a.created_at AS event_time,
                    'appointment_scheduled' AS event_type,
                    'Appointment scheduled' AS title,
                    COALESCE(a.appointment_type, 'Appointment') AS detail,
                    6 AS sort_order
                FROM appointments a
                WHERE a.enrollment_id = %s

                UNION ALL

                SELECT
                    a.appointment_date AS event_time,
                    'appointment_due' AS event_type,
                    'Appointment date' AS title,
                    COALESCE(a.appointment_type, 'Appointment') AS detail,
                    7 AS sort_order
                FROM appointments a
                WHERE a.enrollment_id = %s
            ) timeline_items
            WHERE event_time IS NOT NULL
            ORDER BY event_time DESC, sort_order DESC
            """,
            """
            SELECT
                event_time,
                event_type,
                title,
                detail,
                sort_order
            FROM (
                SELECT
                    pe.created_at AS event_time,
                    'enrollment_started' AS event_type,
                    'Program enrollment started' AS title,
                    'Status: ' || COALESCE(pe.program_status, 'active') AS detail,
                    1 AS sort_order
                FROM program_enrollments pe
                WHERE pe.id = ?

                UNION ALL

                SELECT
                    g.created_at AS event_time,
                    'goal_created' AS event_type,
                    'Goal created' AS title,
                    g.goal_text AS detail,
                    2 AS sort_order
                FROM goals g
                WHERE g.enrollment_id = ?

                UNION ALL

                SELECT
                    g.completed_date AS event_time,
                    'goal_completed' AS event_type,
                    'Goal completed' AS title,
                    g.goal_text AS detail,
                    3 AS sort_order
                FROM goals g
                WHERE g.enrollment_id = ?
                  AND g.completed_date IS NOT NULL

                UNION ALL

                SELECT
                    COALESCE(cmu.meeting_date, cmu.created_at) AS event_time,
                    'case_note' AS event_type,
                    'Case manager note' AS title,
                    COALESCE(cmu.notes, cmu.progress_notes, cmu.action_items, 'Case update recorded') AS detail,
                    4 AS sort_order
                FROM case_manager_updates cmu
                WHERE cmu.enrollment_id = ?

                UNION ALL

                SELECT
                    wrs.submitted_at AS event_time,
                    'compliance_submitted' AS event_type,
                    'Weekly compliance submitted' AS title,
                    'Productive Hours: ' || COALESCE(CAST(wrs.productive_hours AS TEXT), '0') ||
                    ' | Work Hours: ' || COALESCE(CAST(wrs.work_hours AS TEXT), '0') ||
                    ' | Meetings: ' || COALESCE(CAST(wrs.meeting_count AS TEXT), '0') AS detail,
                    5 AS sort_order
                FROM weekly_resident_summary wrs
                WHERE wrs.enrollment_id = ?

                UNION ALL

                SELECT
                    a.created_at AS event_time,
                    'appointment_scheduled' AS event_type,
                    'Appointment scheduled' AS title,
                    COALESCE(a.appointment_type, 'Appointment') AS detail,
                    6 AS sort_order
                FROM appointments a
                WHERE a.enrollment_id = ?

                UNION ALL

                SELECT
                    a.appointment_date AS event_time,
                    'appointment_due' AS event_type,
                    'Appointment date' AS title,
                    COALESCE(a.appointment_type, 'Appointment') AS detail,
                    7 AS sort_order
                FROM appointments a
                WHERE a.enrollment_id = ?
            ) timeline_items
            WHERE event_time IS NOT NULL
            ORDER BY event_time DESC, sort_order DESC
            """,
        ),
        (
            enrollment_id,
            enrollment_id,
            enrollment_id,
            enrollment_id,
            enrollment_id,
            enrollment_id,
            enrollment_id,
        ),
    )


@resident_detail.route("/<int:resident_id>")
@require_login
@require_shelter
def resident_profile(resident_id: int):
    shelter = session.get("shelter")

    resident = db_fetchone(
        _sql(
            """
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                r.shelter AS resident_shelter,
                r.is_active,
                pe.id AS enrollment_id,
                pe.shelter AS enrollment_shelter,
                pe.program_status,
                pe.entry_date,
                pe.exit_date
            FROM residents r
            LEFT JOIN program_enrollments pe
                ON pe.resident_id = r.id
            WHERE r.id = %s AND r.shelter = %s
            ORDER BY pe.id DESC
            LIMIT 1
            """,
            """
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                r.shelter AS resident_shelter,
                r.is_active,
                pe.id AS enrollment_id,
                pe.shelter AS enrollment_shelter,
                pe.program_status,
                pe.entry_date,
                pe.exit_date
            FROM residents r
            LEFT JOIN program_enrollments pe
                ON pe.resident_id = r.id
            WHERE r.id = ? AND r.shelter = ?
            ORDER BY pe.id DESC
            LIMIT 1
            """,
        ),
        (resident_id, shelter),
    )

    if not resident:
        return render_template(
            "resident_detail/profile.html",
            resident=None,
            compliance=None,
            goals=[],
            notes=[],
            appointment=None,
            timeline=[],
        )

    enrollment_id = resident["enrollment_id"] if isinstance(resident, dict) else resident[5]

    compliance = None
    goals = []
    notes = []
    appointment = None
    timeline = []

    if enrollment_id:
        compliance = db_fetchone(
            _sql(
                """
                SELECT
                    productive_hours,
                    work_hours,
                    meeting_count,
                    submitted_at
                FROM weekly_resident_summary
                WHERE enrollment_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                """
                SELECT
                    productive_hours,
                    work_hours,
                    meeting_count,
                    submitted_at
                FROM weekly_resident_summary
                WHERE enrollment_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
            ),
            (enrollment_id,),
        )

        goals = db_fetchall(
            _sql(
                """
                SELECT
                    id,
                    goal_text,
                    status,
                    target_date,
                    created_at,
                    completed_date
                FROM goals
                WHERE enrollment_id = %s
                ORDER BY created_at DESC
                """,
                """
                SELECT
                    id,
                    goal_text,
                    status,
                    target_date,
                    created_at,
                    completed_date
                FROM goals
                WHERE enrollment_id = ?
                ORDER BY created_at DESC
                """,
            ),
            (enrollment_id,),
        )

        notes = db_fetchall(
            _sql(
                """
                SELECT
                    meeting_date,
                    notes,
                    progress_notes,
                    action_items,
                    created_at
                FROM case_manager_updates
                WHERE enrollment_id = %s
                ORDER BY meeting_date DESC, id DESC
                """,
                """
                SELECT
                    meeting_date,
                    notes,
                    progress_notes,
                    action_items,
                    created_at
                FROM case_manager_updates
                WHERE enrollment_id = ?
                ORDER BY meeting_date DESC, id DESC
                """,
            ),
            (enrollment_id,),
        )

        appointment = db_fetchone(
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
                ORDER BY appointment_date ASC, id ASC
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
                ORDER BY appointment_date ASC, id ASC
                LIMIT 1
                """,
            ),
            (enrollment_id,),
        )

        timeline = _load_timeline(enrollment_id)

    return render_template(
        "resident_detail/profile.html",
        resident=resident,
        compliance=compliance,
        goals=goals,
        notes=notes,
        appointment=appointment,
        timeline=timeline,
    )


@resident_detail.post("/<int:resident_id>/enroll")
@require_login
@require_shelter
def create_enrollment(resident_id: int):
    shelter = session.get("shelter")

    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    resident = db_fetchone(
        _sql(
            """
            SELECT
                id,
                shelter
            FROM residents
            WHERE id = %s AND shelter = %s
            """,
            """
            SELECT
                id,
                shelter
            FROM residents
            WHERE id = ? AND shelter = ?
            """,
        ),
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    existing = db_fetchone(
        _sql(
            """
            SELECT
                id
            FROM program_enrollments
            WHERE resident_id = %s AND program_status = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            """
            SELECT
                id
            FROM program_enrollments
            WHERE resident_id = ? AND program_status = ?
            ORDER BY id DESC
            LIMIT 1
            """,
        ),
        (resident_id, "active"),
    )

    if existing:
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
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))


@resident_detail.post("/<int:resident_id>/goals")
@require_login
@require_shelter
def add_goal(resident_id: int):
    shelter = session.get("shelter")

    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    resident = _resident_enrollment_for_shelter(resident_id, shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    enrollment_id = resident["enrollment_id"] if isinstance(resident, dict) else resident[1]

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
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))


@resident_detail.post("/goal/<int:goal_id>/complete")
@require_login
@require_shelter
def complete_goal(goal_id: int):
    shelter = session.get("shelter")

    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("residents.staff_residents"))

    goal = db_fetchone(
        _sql(
            """
            SELECT
                g.id,
                r.id AS resident_id
            FROM goals g
            JOIN program_enrollments pe
                ON pe.id = g.enrollment_id
            JOIN residents r
                ON r.id = pe.resident_id
            WHERE g.id = %s
              AND r.shelter = %s
            """,
            """
            SELECT
                g.id,
                r.id AS resident_id
            FROM goals g
            JOIN program_enrollments pe
                ON pe.id = g.enrollment_id
            JOIN residents r
                ON r.id = pe.resident_id
            WHERE g.id = ?
              AND r.shelter = ?
            """,
        ),
        (goal_id, shelter),
    )

    if not goal:
        flash("Goal not found or not accessible.", "error")
        return redirect(url_for("residents.staff_residents"))

    resident_id = goal["resident_id"] if isinstance(goal, dict) else goal[1]
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
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))


@resident_detail.post("/<int:resident_id>/case-note")
@require_login
@require_shelter
def add_case_note(resident_id: int):
    shelter = session.get("shelter")
    staff_user_id = session.get("staff_user_id")

    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    resident = _resident_enrollment_for_shelter(resident_id, shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    enrollment_id = resident["enrollment_id"] if isinstance(resident, dict) else resident[1]

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
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))


@resident_detail.post("/<int:resident_id>/appointments")
@require_login
@require_shelter
def add_appointment(resident_id: int):
    shelter = session.get("shelter")

    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    resident = _resident_enrollment_for_shelter(resident_id, shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    enrollment_id = resident["enrollment_id"] if isinstance(resident, dict) else resident[1]

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
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))
