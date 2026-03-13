from __future__ import annotations

from datetime import datetime, timedelta
from flask import Blueprint, render_template, session

from core.auth import require_login, require_shelter
from core.db import db_fetchall

case_dashboard = Blueprint(
    "case_dashboard",
    __name__,
    url_prefix="/staff/case-dashboard",
)


@case_dashboard.route("")
@require_login
@require_shelter
def dashboard():

    shelter = session.get("shelter")
    role = session.get("role")

    # Residents missing enrollment
    missing_enrollment = db_fetchall(
        """
        SELECT r.id, r.first_name, r.last_name, r.shelter
        FROM residents r
        LEFT JOIN program_enrollments pe
        ON pe.resident_id = r.id
        WHERE pe.id IS NULL
        AND r.is_active = 1
        """
    )

    # Residents with no goals
    no_goals = db_fetchall(
        """
        SELECT r.id, r.first_name, r.last_name, r.shelter
        FROM residents r
        JOIN program_enrollments pe ON pe.resident_id = r.id
        LEFT JOIN goals g ON g.enrollment_id = pe.id
        WHERE g.id IS NULL
        """
    )

    # Compliance missing this week
    compliance_missing = db_fetchall(
        """
        SELECT r.id, r.first_name, r.last_name, r.shelter
        FROM residents r
        JOIN program_enrollments pe ON pe.resident_id = r.id
        LEFT JOIN weekly_resident_summary wrs
        ON wrs.enrollment_id = pe.id
        AND wrs.submitted_at >= DATE('now','-7 day')
        WHERE wrs.id IS NULL
        """
    )

    # No case notes recently
    notes_missing = db_fetchall(
        """
        SELECT r.id, r.first_name, r.last_name, r.shelter
        FROM residents r
        JOIN program_enrollments pe ON pe.resident_id = r.id
        LEFT JOIN case_manager_updates cmu
        ON cmu.enrollment_id = pe.id
        AND cmu.created_at >= DATE('now','-14 day')
        WHERE cmu.id IS NULL
        """
    )

    # No appointments scheduled
    no_appointments = db_fetchall(
        """
        SELECT r.id, r.first_name, r.last_name, r.shelter
        FROM residents r
        JOIN program_enrollments pe ON pe.resident_id = r.id
        LEFT JOIN appointments a
        ON a.enrollment_id = pe.id
        WHERE a.id IS NULL
        """
    )

    return render_template(
        "case_dashboard/dashboard.html",
        missing_enrollment=missing_enrollment,
        no_goals=no_goals,
        compliance_missing=compliance_missing,
        notes_missing=notes_missing,
        no_appointments=no_appointments,
        role=role,
        shelter=shelter,
    )
