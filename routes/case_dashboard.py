from __future__ import annotations

from flask import Blueprint, g, render_template, session

from core.auth import require_login, require_shelter
from core.db import db_fetchall

case_dashboard = Blueprint(
    "case_dashboard",
    __name__,
    url_prefix="/staff/case-dashboard",
)


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


@case_dashboard.route("")
@require_login
@require_shelter
def dashboard():
    shelter = session.get("shelter")
    role = session.get("role")

    if role in {"admin", "shelter_director", "supervisor"}:
        shelter_filter = ""
        params: tuple = ()
    else:
        shelter_filter = "AND r.shelter = %s" if g.get("db_kind") == "pg" else "AND r.shelter = ?"
        params = (shelter,)

    # Residents missing enrollment
    missing_enrollment = db_fetchall(
        _sql(
            f"""
            SELECT r.id, r.first_name, r.last_name, r.shelter
            FROM residents r
            LEFT JOIN program_enrollments pe
              ON pe.resident_id = r.id
            WHERE pe.id IS NULL
              AND r.is_active = TRUE
              {shelter_filter}
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
            f"""
            SELECT r.id, r.first_name, r.last_name, r.shelter
            FROM residents r
            LEFT JOIN program_enrollments pe
              ON pe.resident_id = r.id
            WHERE pe.id IS NULL
              AND r.is_active = 1
              {shelter_filter}
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
        ),
        params,
    )

    # Residents with no goals
    no_goals = db_fetchall(
        _sql(
            f"""
            SELECT DISTINCT r.id, r.first_name, r.last_name, r.shelter
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN goals g
              ON g.enrollment_id = pe.id
            WHERE g.id IS NULL
              AND r.is_active = TRUE
              {shelter_filter}
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
            f"""
            SELECT DISTINCT r.id, r.first_name, r.last_name, r.shelter
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN goals g
              ON g.enrollment_id = pe.id
            WHERE g.id IS NULL
              AND r.is_active = 1
              {shelter_filter}
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
        ),
        params,
    )

    # Compliance missing this week
    compliance_missing = db_fetchall(
        _sql(
            f"""
            SELECT DISTINCT r.id, r.first_name, r.last_name, r.shelter
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN weekly_resident_summary wrs
              ON wrs.enrollment_id = pe.id
             AND wrs.submitted_at >= NOW() - INTERVAL '7 days'
            WHERE wrs.submitted_at IS NULL
              AND r.is_active = TRUE
              {shelter_filter}
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
            f"""
            SELECT DISTINCT r.id, r.first_name, r.last_name, r.shelter
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN weekly_resident_summary wrs
              ON wrs.enrollment_id = pe.id
             AND wrs.submitted_at >= DATE('now','-7 day')
            WHERE wrs.submitted_at IS NULL
              AND r.is_active = 1
              {shelter_filter}
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
        ),
        params,
    )

    # No case notes recently
    notes_missing = db_fetchall(
        _sql(
            f"""
            SELECT DISTINCT r.id, r.first_name, r.last_name, r.shelter
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN case_manager_updates cmu
              ON cmu.enrollment_id = pe.id
             AND cmu.created_at >= NOW() - INTERVAL '14 days'
            WHERE cmu.id IS NULL
              AND r.is_active = TRUE
              {shelter_filter}
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
            f"""
            SELECT DISTINCT r.id, r.first_name, r.last_name, r.shelter
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN case_manager_updates cmu
              ON cmu.enrollment_id = pe.id
             AND cmu.created_at >= DATE('now','-14 day')
            WHERE cmu.id IS NULL
              AND r.is_active = 1
              {shelter_filter}
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
        ),
        params,
    )

    # No appointments scheduled
    no_appointments = db_fetchall(
        _sql(
            f"""
            SELECT DISTINCT r.id, r.first_name, r.last_name, r.shelter
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN appointments a
              ON a.enrollment_id = pe.id
            WHERE a.id IS NULL
              AND r.is_active = TRUE
              {shelter_filter}
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
            f"""
            SELECT DISTINCT r.id, r.first_name, r.last_name, r.shelter
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN appointments a
              ON a.enrollment_id = pe.id
            WHERE a.id IS NULL
              AND r.is_active = 1
              {shelter_filter}
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
        ),
        params,
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
