from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone

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


@resident_detail.route("/<int:resident_id>/goals", methods=["POST"])
@require_login
@require_shelter
def add_goal(resident_id: int):
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
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    if isinstance(resident, dict):
        enrollment_id = resident.get("enrollment_id")
    else:
        enrollment_id = resident[4]

    if not enrollment_id:
        flash("This resident does not have a program enrollment yet. Add enrollment before creating a goal.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    goal_text = (request.form.get("goal_text") or "").strip()
    target_date = (request.form.get("target_date") or "").strip()

    if not goal_text:
        flash("Goal text is required.", "error")
        return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))

    now = datetime.utcnow().isoformat()

    db_execute(
        _sql(
            """
            INSERT INTO goals (
                enrollment_id,
                goal_text,
                status,
                target_date,
                completed_date,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            """
            INSERT INTO goals (
                enrollment_id,
                goal_text,
                status,
                target_date,
                completed_date,
                created_at,
                updated_at
            )
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

    flash("Goal added.", "success")
    return redirect(url_for("resident_detail.resident_profile", resident_id=resident_id))
