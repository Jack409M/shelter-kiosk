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
        )

    if isinstance(resident, dict):
        enrollment_id = resident.get("enrollment_id")
    else:
        enrollment_id = resident[4]

    compliance = None
    goals = []
    notes = []
    appointment = None

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

    return render_template(
        "resident_detail/profile.html",
        resident=resident,
        compliance=compliance,
        goals=goals,
        notes=notes,
        appointment=appointment,
    )


@resident_detail.post("/<int:resident_id>/case-note")
@require_login
@require_shelter
def add_case_note(resident_id: int):
    shelter = session.get("shelter")
    staff_user_id = session.get("staff_user_id")
    role = (session.get("role") or "").strip()

    if role not in {"admin", "shelter_director", "case_manager"}:
        flash("Case manager access required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    resident = db_fetchone(
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

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    enrollment_id = resident["enrollment_id"] if isinstance(resident, dict) else resident[1]

    if not enrollment_id:
        flash("Resident does not have an active enrollment record yet.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    meeting_date = (request.form.get("meeting_date") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    progress_notes = (request.form.get("progress_notes") or "").strip()
    action_items = (request.form.get("action_items") or "").strip()

    if not meeting_date and not notes and not progress_notes and not action_items:
        flash("Enter at least one case manager note field.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    db_execute(
        _sql(
            """
            INSERT INTO case_manager_updates
            (enrollment_id, meeting_date, notes, progress_notes, action_items, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            """
            INSERT INTO case_manager_updates
            (enrollment_id, meeting_date, notes, progress_notes, action_items, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
        ),
        (
            enrollment_id,
            meeting_date or None,
            notes or None,
            progress_notes or None,
            action_items or None,
            utcnow_iso(),
        ),
    )

    flash("Case manager note added.", "ok")
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))
