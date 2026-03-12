from __future__ import annotations

from flask import Blueprint, render_template

from core.auth import require_login
from core.db import db_fetchall, db_fetchone

resident_detail = Blueprint(
    "resident_detail",
    __name__,
    url_prefix="/staff/resident"
)


@resident_detail.route("/<int:resident_id>")
@require_login
def resident_profile(resident_id):

    resident = db_fetchone(
        """
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            pe.program_status,
            pe.level,
            pe.enrolled_at
        FROM residents r
        LEFT JOIN program_enrollments pe
            ON pe.resident_id = r.id
        WHERE r.id = %s
        """
        if False else
        """
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            pe.program_status,
            pe.level,
            pe.enrolled_at
        FROM residents r
        LEFT JOIN program_enrollments pe
            ON pe.resident_id = r.id
        WHERE r.id = ?
        """,
        (resident_id,)
    )

    compliance = db_fetchone(
        """
        SELECT
            productive_hours,
            work_hours,
            meeting_count
        FROM weekly_resident_summary
        WHERE enrollment_id = (
            SELECT id FROM program_enrollments
            WHERE resident_id = %s
        )
        """
        if False else
        """
        SELECT
            productive_hours,
            work_hours,
            meeting_count
        FROM weekly_resident_summary
        WHERE enrollment_id = (
            SELECT id FROM program_enrollments
            WHERE resident_id = ?
        )
        """,
        (resident_id,)
    )

    goals = db_fetchall(
        """
        SELECT
            goal_text,
            status,
            created_at
        FROM goals
        WHERE resident_id = ?
        ORDER BY created_at DESC
        """,
        (resident_id,)
    )

    notes = db_fetchall(
        """
        SELECT
            note_text,
            created_at
        FROM case_manager_updates
        WHERE resident_id = ?
        ORDER BY created_at DESC
        """,
        (resident_id,)
    )

    appointment = db_fetchone(
        """
        SELECT
            scheduled_at
        FROM appointments
        WHERE resident_id = ?
        ORDER BY scheduled_at ASC
        LIMIT 1
        """,
        (resident_id,)
    )

    return render_template(
        "resident_detail/profile.html",
        resident=resident,
        compliance=compliance,
        goals=goals,
        notes=notes,
        appointment=appointment
    )
