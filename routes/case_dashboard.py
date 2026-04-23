from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, g, render_template, session

from core.auth import require_login, require_shelter
from core.db import db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.pass_retention import run_pass_retention_cleanup_for_shelter
from routes.case_management_parts.helpers import current_enrollment_order_sql

case_dashboard = Blueprint(
    "case_dashboard",
    __name__,
    url_prefix="/staff/case-dashboard",
)

CHICAGO_TZ = ZoneInfo("America/Chicago")


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
        return dt.replace(tzinfo=UTC)

    return dt.astimezone(UTC)


def _to_chicago(value):
    dt = _parse_dt(value)
    if not dt:
        return None
    return dt.astimezone(CHICAGO_TZ)


def _scope_filter_and_params(shelter: str | None):
    filter_sql = (
        "AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(%s))"
        if g.get("db_kind") == "pg"
        else "AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(?))"
    )
    return filter_sql, (shelter,)


def _request_placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _row_value(row, key: str, index: int):
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


@case_dashboard.route("")
@require_login
@require_shelter
def dashboard():
    shelter = session.get("shelter")
    role = session.get("role")

    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())

    shelter_filter, params = _scope_filter_and_params(shelter)
    placeholder = _request_placeholder()

    pending_pass_count_row = db_fetchone(
        f"""
        SELECT COUNT(*) AS count
        FROM resident_passes
        WHERE status = {placeholder}
          AND LOWER(TRIM(shelter)) = LOWER(TRIM({placeholder}))
        """,
        ("pending", shelter),
    )

    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    approved_pass_count_row = db_fetchone(
        _sql(
            f"""
            SELECT COUNT(DISTINCT rp.resident_id) AS count
            FROM resident_passes rp
            JOIN residents r
              ON r.id = rp.resident_id
             AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(rp.shelter))
            WHERE rp.status = {placeholder}
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM({placeholder}))
              AND r.is_active = TRUE
              AND (
                    (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= {placeholder} AND rp.end_at >= {placeholder})
                 OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= {placeholder} AND rp.end_date >= {placeholder})
              )
              AND EXISTS (
                    SELECT 1
                    FROM attendance_events ae
                    WHERE ae.id = (
                        SELECT ae2.id
                        FROM attendance_events ae2
                        WHERE ae2.resident_id = rp.resident_id
                          AND LOWER(TRIM(ae2.shelter)) = LOWER(TRIM(rp.shelter))
                        ORDER BY ae2.event_time DESC, ae2.id DESC
                        LIMIT 1
                    )
                      AND ae.event_type = 'check_out'
              )
            """,
            f"""
            SELECT COUNT(DISTINCT rp.resident_id) AS count
            FROM resident_passes rp
            JOIN residents r
              ON r.id = rp.resident_id
             AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(rp.shelter))
            WHERE rp.status = {placeholder}
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM({placeholder}))
              AND r.is_active = 1
              AND (
                    (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= {placeholder} AND rp.end_at >= {placeholder})
                 OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= {placeholder} AND rp.end_date >= {placeholder})
              )
              AND EXISTS (
                    SELECT 1
                    FROM attendance_events ae
                    WHERE ae.id = (
                        SELECT ae2.id
                        FROM attendance_events ae2
                        WHERE ae2.resident_id = rp.resident_id
                          AND LOWER(TRIM(ae2.shelter)) = LOWER(TRIM(rp.shelter))
                        ORDER BY ae2.event_time DESC, ae2.id DESC
                        LIMIT 1
                    )
                      AND ae.event_type = 'check_out'
              )
            """,
        ),
        ("approved", shelter, now_iso, now_iso, today_iso, today_iso),
    )

    pending_transport_count_row = db_fetchone(
        f"""
        SELECT COUNT(*) AS count
        FROM transport_requests
        WHERE status = {placeholder}
          AND LOWER(TRIM(shelter)) = LOWER(TRIM({placeholder}))
        """,
        ("pending", shelter),
    )

    intake_drafts_count_row = db_fetchone(
        f"""
        SELECT COUNT(*) AS count
        FROM intake_drafts
        WHERE LOWER(COALESCE(TRIM(shelter), '')) = LOWER(TRIM({placeholder}))
          AND status = 'draft'
        """,
        (shelter,),
    )

    family_intakes_pending_rows = db_fetchall(
        _sql(
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                COALESCE(fs.kids_at_dwc, 0) + COALESCE(fs.kids_served_outside_under_18, 0) AS expected_children,
                COUNT(rc.id) AS actual_children
            FROM residents r
            JOIN program_enrollments pe
              ON pe.id = (
                SELECT pe2.id
                FROM program_enrollments pe2
                WHERE pe2.resident_id = r.id
                ORDER BY {current_enrollment_order_sql("pe2")}
                LIMIT 1
              )
            JOIN family_snapshots fs
              ON fs.id = (
                SELECT fs2.id
                FROM family_snapshots fs2
                WHERE fs2.enrollment_id = pe.id
                ORDER BY fs2.id DESC
                LIMIT 1
              )
            LEFT JOIN resident_children rc
              ON rc.resident_id = r.id
             AND rc.is_active = TRUE
            WHERE r.is_active = TRUE
              AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(%s))
            GROUP BY
                r.id,
                r.first_name,
                r.last_name,
                fs.kids_at_dwc,
                fs.kids_served_outside_under_18
            HAVING (COALESCE(fs.kids_at_dwc, 0) + COALESCE(fs.kids_served_outside_under_18, 0)) > COUNT(rc.id)
            ORDER BY r.last_name, r.first_name, r.id
            """,
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                COALESCE(fs.kids_at_dwc, 0) + COALESCE(fs.kids_served_outside_under_18, 0) AS expected_children,
                COUNT(rc.id) AS actual_children
            FROM residents r
            JOIN program_enrollments pe
              ON pe.id = (
                SELECT pe2.id
                FROM program_enrollments pe2
                WHERE pe2.resident_id = r.id
                ORDER BY {current_enrollment_order_sql("pe2")}
                LIMIT 1
              )
            JOIN family_snapshots fs
              ON fs.id = (
                SELECT fs2.id
                FROM family_snapshots fs2
                WHERE fs2.enrollment_id = pe.id
                ORDER BY fs2.id DESC
                LIMIT 1
              )
            LEFT JOIN resident_children rc
              ON rc.resident_id = r.id
             AND rc.is_active = 1
            WHERE r.is_active = 1
              AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(?))
            GROUP BY
                r.id,
                r.first_name,
                r.last_name,
                fs.kids_at_dwc,
                fs.kids_served_outside_under_18
            HAVING (COALESCE(fs.kids_at_dwc, 0) + COALESCE(fs.kids_served_outside_under_18, 0)) > COUNT(rc.id)
            ORDER BY r.last_name, r.first_name, r.id
            """,
        ),
        (shelter,),
    )

    pending_pass_count = (
        pending_pass_count_row["count"]
        if isinstance(pending_pass_count_row, dict) and "count" in pending_pass_count_row
        else pending_pass_count_row[0]
        if pending_pass_count_row
        else 0
    )
    approved_pass_count = (
        approved_pass_count_row["count"]
        if isinstance(approved_pass_count_row, dict) and "count" in approved_pass_count_row
        else approved_pass_count_row[0]
        if approved_pass_count_row
        else 0
    )
    pending_transport_count = (
        pending_transport_count_row["count"]
        if isinstance(pending_transport_count_row, dict) and "count" in pending_transport_count_row
        else pending_transport_count_row[0]
        if pending_transport_count_row
        else 0
    )
    intake_drafts_count = (
        intake_drafts_count_row["count"]
        if isinstance(intake_drafts_count_row, dict) and "count" in intake_drafts_count_row
        else intake_drafts_count_row[0]
        if intake_drafts_count_row
        else 0
    )
    family_intakes_pending_count = len(family_intakes_pending_rows)

    now_chicago = datetime.now(CHICAGO_TZ)
    today_local = now_chicago.date()
    yesterday_local = today_local - timedelta(days=1)
    month_start_local = today_local.replace(day=1)
    month_end_local = (month_start_local + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    level9_review_cutoff = today_local + timedelta(days=14)

    attendance_rows = db_fetchall(
        _sql(
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                r.shelter,
                ae.event_type,
                ae.event_time,
                ae.expected_back_time,
                ae.note
            FROM residents r
            LEFT JOIN attendance_events ae
              ON ae.id = (
                SELECT ae2.id
                FROM attendance_events ae2
                WHERE ae2.resident_id = r.id
                  AND LOWER(TRIM(ae2.shelter)) = LOWER(TRIM(r.shelter))
                ORDER BY ae2.event_time DESC, ae2.id DESC
                LIMIT 1
              )
            WHERE r.is_active = TRUE
              {shelter_filter}
            ORDER BY r.last_name, r.first_name
            """,
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                r.shelter,
                ae.event_type,
                ae.event_time,
                ae.expected_back_time,
                ae.note
            FROM residents r
            LEFT JOIN attendance_events ae
              ON ae.id = (
                SELECT ae2.id
                FROM attendance_events ae2
                WHERE ae2.resident_id = r.id
                  AND LOWER(TRIM(ae2.shelter)) = LOWER(TRIM(r.shelter))
                ORDER BY ae2.event_time DESC, ae2.id DESC
                LIMIT 1
              )
            WHERE r.is_active = 1
              {shelter_filter}
            ORDER BY r.last_name, r.first_name
            """,
        ),
        params,
    )

    missed_clock_in_rows = []
    for row in attendance_rows:
        event_type = _row_value(row, "event_type", 4)
        expected_back_time = _row_value(row, "expected_back_time", 6)

        if event_type != "check_out":
            continue

        expected_back_local = _to_chicago(expected_back_time)
        if not expected_back_local:
            continue

        if expected_back_local.date() < today_local:
            missed_clock_in_rows.append(
                {
                    "id": _row_value(row, "id", 0),
                    "first_name": _row_value(row, "first_name", 1),
                    "last_name": _row_value(row, "last_name", 2),
                    "expected_back_local": expected_back_local,
                }
            )

    late_check_in_rows_raw = db_fetchall(
        _sql(
            """
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                ci.event_time AS check_in_time,
                co.expected_back_time
            FROM attendance_events ci
            JOIN residents r
              ON r.id = ci.resident_id
             AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(ci.shelter))
            JOIN attendance_events co
              ON co.id = (
                SELECT co2.id
                FROM attendance_events co2
                WHERE co2.resident_id = ci.resident_id
                  AND LOWER(TRIM(co2.shelter)) = LOWER(TRIM(ci.shelter))
                  AND co2.event_type = 'check_out'
                  AND co2.event_time < ci.event_time
                ORDER BY co2.event_time DESC, co2.id DESC
                LIMIT 1
              )
            WHERE ci.event_type = 'check_in'
              AND r.is_active = TRUE
              AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(%s))
            ORDER BY ci.event_time DESC
            """,
            """
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                ci.event_time AS check_in_time,
                co.expected_back_time
            FROM attendance_events ci
            JOIN residents r
              ON r.id = ci.resident_id
             AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(ci.shelter))
            JOIN attendance_events co
              ON co.id = (
                SELECT co2.id
                FROM attendance_events co2
                WHERE co2.resident_id = ci.resident_id
                  AND LOWER(TRIM(co2.shelter)) = LOWER(TRIM(ci.shelter))
                  AND co2.event_type = 'check_out'
                  AND co2.event_time < ci.event_time
                ORDER BY co2.event_time DESC, co2.id DESC
                LIMIT 1
              )
            WHERE ci.event_type = 'check_in'
              AND r.is_active = 1
              AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(?))
            ORDER BY ci.event_time DESC
            """,
        ),
        (shelter,),
    )

    late_check_in_rows = []
    for row in late_check_in_rows_raw:
        check_in_local = _to_chicago(_row_value(row, "check_in_time", 3))
        expected_back_local = _to_chicago(_row_value(row, "expected_back_time", 4))

        if not check_in_local or not expected_back_local:
            continue

        if check_in_local.date() != yesterday_local:
            continue

        if check_in_local > expected_back_local:
            late_check_in_rows.append(
                {
                    "id": _row_value(row, "id", 0),
                    "first_name": _row_value(row, "first_name", 1),
                    "last_name": _row_value(row, "last_name", 2),
                    "check_in_local": check_in_local,
                    "expected_back_local": expected_back_local,
                }
            )

    appointments_today_rows = db_fetchall(
        _sql(
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                a.appointment_type,
                a.appointment_date,
                a.notes
            FROM residents r
            JOIN program_enrollments pe
              ON pe.id = (
                SELECT pe2.id
                FROM program_enrollments pe2
                WHERE pe2.resident_id = r.id
                ORDER BY {current_enrollment_order_sql("pe2")}
                LIMIT 1
              )
            JOIN appointments a
              ON a.enrollment_id = pe.id
            WHERE r.is_active = TRUE
              AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(%s))
              AND a.appointment_date = %s
            ORDER BY r.last_name, r.first_name, a.id
            """,
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                a.appointment_type,
                a.appointment_date,
                a.notes
            FROM residents r
            JOIN program_enrollments pe
              ON pe.id = (
                SELECT pe2.id
                FROM program_enrollments pe2
                WHERE pe2.resident_id = r.id
                ORDER BY {current_enrollment_order_sql("pe2")}
                LIMIT 1
              )
            JOIN appointments a
              ON a.enrollment_id = pe.id
            WHERE r.is_active = 1
              AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(?))
              AND a.appointment_date = ?
            ORDER BY r.last_name, r.first_name, a.id
            """,
        ),
        (shelter, today_local.isoformat()),
    )

    appointments_today = []
    for row in appointments_today_rows:
        appointments_today.append(
            {
                "id": _row_value(row, "id", 0),
                "first_name": _row_value(row, "first_name", 1),
                "last_name": _row_value(row, "last_name", 2),
                "appointment_type": _row_value(row, "appointment_type", 3),
                "appointment_date": _row_value(row, "appointment_date", 4),
                "notes": _row_value(row, "notes", 5),
            }
        )

    yesterday = today_local - timedelta(days=1)

    missed_yesterday_rows = db_fetchall(
        _sql(
            """
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                ct.name AS chore_name
            FROM chore_assignments ca
            JOIN residents r ON r.id = ca.resident_id
            JOIN chore_templates ct ON ct.id = ca.chore_id
            WHERE r.is_active = TRUE
              AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(%s))
              AND ca.assigned_date = %s
              AND ca.status <> 'completed'
            ORDER BY r.last_name, r.first_name
            """,
            """
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                ct.name AS chore_name
            FROM chore_assignments ca
            JOIN residents r ON r.id = ca.resident_id
            JOIN chore_templates ct ON ct.id = ca.chore_id
            WHERE r.is_active = 1
              AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(?))
              AND ca.assigned_date = ?
              AND ca.status <> 'completed'
            ORDER BY r.last_name, r.first_name
            """,
        ),
        (shelter, yesterday.isoformat()),
    )

    weekday = today_local.weekday()
    days_to_tuesday = (weekday - 1) % 7
    week_start = today_local - timedelta(days=days_to_tuesday)

    missed_week_rows = db_fetchall(
        _sql(
            """
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                COUNT(*) AS missed_count
            FROM chore_assignments ca
            JOIN residents r ON r.id = ca.resident_id
            WHERE r.is_active = TRUE
              AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(%s))
              AND ca.assigned_date BETWEEN %s AND %s
              AND ca.status <> 'completed'
            GROUP BY r.id, r.first_name, r.last_name
            HAVING COUNT(*) > 0
            ORDER BY missed_count DESC, r.last_name, r.first_name
            """,
            """
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                COUNT(*) AS missed_count
            FROM chore_assignments ca
            JOIN residents r ON r.id = ca.resident_id
            WHERE r.is_active = 1
              AND LOWER(TRIM(r.shelter)) = LOWER(TRIM(?))
              AND ca.assigned_date BETWEEN ? AND ?
              AND ca.status <> 'completed'
            GROUP BY r.id, r.first_name, r.last_name
            HAVING COUNT(*) > 0
            ORDER BY missed_count DESC, r.last_name, r.first_name
            """,
        ),
        (shelter, week_start.isoformat(), today_local.isoformat()),
    )

    level9_active_count_row = db_fetchone(
        _sql(
            f"""
            SELECT COUNT(*) AS count
            FROM level9_support_lifecycles l9
            JOIN residents r ON r.id = l9.resident_id
            WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM(%s))
              AND r.is_active = TRUE
              AND l9.status IN (%s, %s)
            """,
            f"""
            SELECT COUNT(*) AS count
            FROM level9_support_lifecycles l9
            JOIN residents r ON r.id = l9.resident_id
            WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM(?))
              AND r.is_active = 1
              AND l9.status IN (?, ?)
            """,
        ),
        (shelter, "active", "extended_active"),
    )

    level9_due_this_month_count_row = db_fetchone(
        _sql(
            f"""
            SELECT COUNT(*) AS count
            FROM level9_monthly_followups f
            JOIN level9_support_lifecycles l9 ON l9.id = f.level9_lifecycle_id
            JOIN residents r ON r.id = l9.resident_id
            WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM(%s))
              AND r.is_active = TRUE
              AND f.status = %s
              AND f.due_date BETWEEN %s AND %s
            """,
            f"""
            SELECT COUNT(*) AS count
            FROM level9_monthly_followups f
            JOIN level9_support_lifecycles l9 ON l9.id = f.level9_lifecycle_id
            JOIN residents r ON r.id = l9.resident_id
            WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM(?))
              AND r.is_active = 1
              AND f.status = ?
              AND f.due_date BETWEEN ? AND ?
            """,
        ),
        (
            shelter,
            "pending",
            month_start_local.isoformat(),
            month_end_local.isoformat(),
        ),
    )

    level9_overdue_rows = db_fetchall(
        _sql(
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                f.support_month_number,
                f.due_date
            FROM level9_monthly_followups f
            JOIN level9_support_lifecycles l9 ON l9.id = f.level9_lifecycle_id
            JOIN residents r ON r.id = l9.resident_id
            WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM(%s))
              AND r.is_active = TRUE
              AND f.status = %s
              AND f.due_date < %s
            ORDER BY f.due_date ASC, r.last_name, r.first_name
            """,
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                f.support_month_number,
                f.due_date
            FROM level9_monthly_followups f
            JOIN level9_support_lifecycles l9 ON l9.id = f.level9_lifecycle_id
            JOIN residents r ON r.id = l9.resident_id
            WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM(?))
              AND r.is_active = 1
              AND f.status = ?
              AND f.due_date < ?
            ORDER BY f.due_date ASC, r.last_name, r.first_name
            """,
        ),
        (shelter, "pending", today_local.isoformat()),
    )

    level9_review_due_rows = db_fetchall(
        _sql(
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                l9.initial_end_date,
                l9.extended_end_date,
                l9.extension_granted,
                l9.status
            FROM level9_support_lifecycles l9
            JOIN residents r ON r.id = l9.resident_id
            WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM(%s))
              AND r.is_active = TRUE
              AND l9.status IN (%s, %s)
              AND l9.initial_end_date BETWEEN %s AND %s
            ORDER BY l9.initial_end_date ASC, r.last_name, r.first_name
            """,
            f"""
            SELECT
                r.id,
                r.first_name,
                r.last_name,
                l9.initial_end_date,
                l9.extended_end_date,
                l9.extension_granted,
                l9.status
            FROM level9_support_lifecycles l9
            JOIN residents r ON r.id = l9.resident_id
            WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM(?))
              AND r.is_active = 1
              AND l9.status IN (?, ?)
              AND l9.initial_end_date BETWEEN ? AND ?
            ORDER BY l9.initial_end_date ASC, r.last_name, r.first_name
            """,
        ),
        (
            shelter,
            "active",
            "extended_active",
            today_local.isoformat(),
            level9_review_cutoff.isoformat(),
        ),
    )

    level9_active_count = (
        level9_active_count_row["count"]
        if isinstance(level9_active_count_row, dict) and "count" in level9_active_count_row
        else level9_active_count_row[0]
        if level9_active_count_row
        else 0
    )
    level9_due_this_month_count = (
        level9_due_this_month_count_row["count"]
        if isinstance(level9_due_this_month_count_row, dict) and "count" in level9_due_this_month_count_row
        else level9_due_this_month_count_row[0]
        if level9_due_this_month_count_row
        else 0
    )
    level9_overdue_count = len(level9_overdue_rows)
    level9_review_due_count = len(level9_review_due_rows)

    return render_template(
        "case_dashboard/dashboard.html",
        pending_pass_count=pending_pass_count,
        approved_pass_count=approved_pass_count,
        pending_transport_count=pending_transport_count,
        intake_drafts_count=intake_drafts_count,
        family_intakes_pending_count=family_intakes_pending_count,
        missed_clock_in_rows=missed_clock_in_rows,
        late_check_in_rows=late_check_in_rows,
        appointments_today=appointments_today,
        missed_yesterday_rows=missed_yesterday_rows,
        missed_week_rows=missed_week_rows,
        level9_active_count=level9_active_count,
        level9_due_this_month_count=level9_due_this_month_count,
        level9_overdue_count=level9_overdue_count,
        level9_review_due_count=level9_review_due_count,
        level9_overdue_rows=level9_overdue_rows,
        level9_review_due_rows=level9_review_due_rows,
        today_local=today_local,
        month_end_local=month_end_local,
        level9_review_cutoff=level9_review_cutoff,
        role=role,
        shelter=shelter,
    )
