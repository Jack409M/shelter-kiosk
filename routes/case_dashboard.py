from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, g, render_template, session

from core.auth import require_login, require_shelter
from core.db import db_fetchall, db_fetchone

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


def _to_chicago(value):
    dt = _parse_dt(value)
    if not dt:
        return None
    return dt.astimezone(ZoneInfo("America/Chicago"))


def _is_recent(value, days: int) -> bool:
    dt = _parse_dt(value)
    if not dt:
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return dt >= cutoff


def _scope_filter_and_params(shelter: str | None):
    filter_sql = "AND r.shelter = %s" if g.get("db_kind") == "pg" else "AND r.shelter = ?"
    return filter_sql, (shelter,)


def _request_placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


@case_dashboard.route("")
@require_login
@require_shelter
def dashboard():
    shelter = session.get("shelter")
    role = session.get("role")

    shelter_filter, params = _scope_filter_and_params(shelter)
    placeholder = _request_placeholder()

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

    pending_pass_count_row = db_fetchone(
        f"""
        SELECT COUNT(*)
        FROM resident_passes
        WHERE status = {placeholder}
          AND shelter = {placeholder}
        """,
        ("pending", shelter),
    )

    pending_transport_count_row = db_fetchone(
        f"""
        SELECT COUNT(*)
        FROM transport_requests
        WHERE status = {placeholder}
          AND shelter = {placeholder}
        """,
        ("pending", shelter),
    )

    pending_pass_count = (
        pending_pass_count_row["count"] if isinstance(pending_pass_count_row, dict) and "count" in pending_pass_count_row
        else pending_pass_count_row[0] if pending_pass_count_row else 0
    )
    pending_transport_count = (
        pending_transport_count_row["count"] if isinstance(pending_transport_count_row, dict) and "count" in pending_transport_count_row
        else pending_transport_count_row[0] if pending_transport_count_row else 0
    )

    pending_pass_rows_raw = db_fetchall(
        _sql(
            """
            SELECT
                rp.id,
                rp.resident_id,
                r.first_name,
                r.last_name,
                rp.shelter,
                rp.pass_type,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.created_at,
                rp.status
            FROM resident_passes rp
            JOIN residents r
              ON r.id = rp.resident_id
            WHERE rp.status = %s
              AND rp.shelter = %s
            ORDER BY rp.created_at ASC
            """,
            """
            SELECT
                rp.id,
                rp.resident_id,
                r.first_name,
                r.last_name,
                rp.shelter,
                rp.pass_type,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.created_at,
                rp.status
            FROM resident_passes rp
            JOIN residents r
              ON r.id = rp.resident_id
            WHERE rp.status = ?
              AND rp.shelter = ?
            ORDER BY rp.created_at ASC
            """,
        ),
        ("pending", shelter),
    )

    pending_pass_rows = []
    now_chicago = datetime.now(ZoneInfo("America/Chicago"))

    for row in pending_pass_rows_raw:
        item = dict(row) if isinstance(row, dict) else {
            "id": row[0],
            "resident_id": row[1],
            "first_name": row[2],
            "last_name": row[3],
            "shelter": row[4],
            "pass_type": row[5],
            "start_at": row[6],
            "end_at": row[7],
            "start_date": row[8],
            "end_date": row[9],
            "destination": row[10],
            "reason": row[11],
            "created_at": row[12],
            "status": row[13],
        }

        item["start_at_local"] = _to_chicago(item.get("start_at"))
        item["end_at_local"] = _to_chicago(item.get("end_at"))
        item["created_at_local"] = _to_chicago(item.get("created_at"))

        is_urgent = False
        if item.get("pass_type") == "ordinary" and item["start_at_local"]:
            delta = item["start_at_local"] - now_chicago
            is_urgent = timedelta(0) <= delta <= timedelta(hours=2)

        item["is_urgent"] = is_urgent
        pending_pass_rows.append(item)

    pending_request_total = int(pending_pass_count or 0) + int(pending_transport_count or 0)

    return render_template(
        "case_dashboard/dashboard.html",
        missing_enrollment=missing_enrollment,
        no_goals=no_goals,
        compliance_missing=compliance_missing,
        notes_missing=notes_missing,
        no_appointments=no_appointments,
        pending_pass_count=pending_pass_count,
        pending_transport_count=pending_transport_count,
        pending_request_total=pending_request_total,
        pending_pass_rows=pending_pass_rows,
        role=role,
        shelter=shelter,
    )
