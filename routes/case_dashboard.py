from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def _parse_dt(value):
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = None

        if dt is None:
            for fmt in (
                "%Y-%m-%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
            ):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue

        if dt is None:
            return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _is_recent(value, days: int) -> bool:
    dt = _parse_dt(value)
    if not dt:
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return dt >= cutoff


def _scope_filter_and_params(shelter: str | None):
    filter_sql = "AND r.shelter = %s" if g.get("db_kind") == "pg" else "AND r.shelter = ?"
    return filter_sql, (shelter,)


@case_dashboard.route("")
@require_login
@require_shelter
def dashboard():
    shelter = session.get("shelter")
    role = session.get("role")

    shelter_filter, params = _scope_filter_and_params(shelter)

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

    compliance_candidates = db_fetchall(
        _sql(
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                r.shelter,
                MAX(wrs.submitted_at) AS last_submitted_at
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN weekly_resident_summary wrs
              ON wrs.enrollment_id = pe.id
            WHERE r.is_active = TRUE
              {shelter_filter}
            GROUP BY r.id, r.first_name, r.last_name, r.shelter
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                r.shelter,
                MAX(wrs.submitted_at) AS last_submitted_at
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN weekly_resident_summary wrs
              ON wrs.enrollment_id = pe.id
            WHERE r.is_active = 1
              {shelter_filter}
            GROUP BY r.id, r.first_name, r.last_name, r.shelter
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
        ),
        params,
    )

    compliance_missing = [
        row for row in compliance_candidates
        if not _is_recent((row.get("last_submitted_at") if isinstance(row, dict) else row[4]), 7)
    ]

    notes_candidates = db_fetchall(
        _sql(
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                r.shelter,
                MAX(cmu.created_at) AS last_note_at
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN case_manager_updates cmu
              ON cmu.enrollment_id = pe.id
            WHERE r.is_active = TRUE
              {shelter_filter}
            GROUP BY r.id, r.first_name, r.last_name, r.shelter
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                r.shelter,
                MAX(cmu.created_at) AS last_note_at
            FROM residents r
            JOIN program_enrollments pe
              ON pe.resident_id = r.id
            LEFT JOIN case_manager_updates cmu
              ON cmu.enrollment_id = pe.id
            WHERE r.is_active = 1
              {shelter_filter}
            GROUP BY r.id, r.first_name, r.last_name, r.shelter
            ORDER BY r.shelter, r.last_name, r.first_name
            """,
        ),
        params,
    )

    notes_missing = [
        row for row in notes_candidates
        if not _is_recent((row.get("last_note_at") if isinstance(row, dict) else row[4]), 14)
    ]

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
