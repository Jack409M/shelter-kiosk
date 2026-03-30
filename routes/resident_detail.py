from __future__ import annotations

from datetime import date, datetime, timedelta

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


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _shelter_equals_sql(column_name: str) -> str:
    if g.get("db_kind") == "pg":
        return f"LOWER(COALESCE({column_name}, '')) = %s"
    return f"LOWER(COALESCE({column_name}, '')) = ?"


def _case_manager_allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


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


def _parse_dt(value):
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def _is_date_only(value) -> bool:
    text = str(value or "").strip()
    return bool(text) and "T" not in text and ":" not in text and len(text) <= 10


def _format_dt(value, *, prefer_date_only: bool = False) -> str:
    if value in (None, ""):
        return "—"

    dt = _parse_dt(value)
    if not dt:
        return str(value)

    date_text = f"{dt.strftime('%b')} {dt.day}, {dt.year}"

    if prefer_date_only or _is_date_only(value):
        return date_text

    time_text = dt.strftime("%I:%M %p").lstrip("0")
    return f"{date_text} {time_text}"


def _format_time_only(value) -> str:
    if value in (None, ""):
        return ""

    dt = _parse_dt(value)
    if not dt:
        return ""

    if _is_date_only(value):
        return "All day"

    return dt.strftime("%I:%M %p").lstrip("0")


def _days_in_program(entry_date_value) -> str:
    entry_dt = _parse_dt(entry_date_value)
    if not entry_dt:
        return "—"

    days = (datetime.utcnow().date() - entry_dt.date()).days
    if days < 0:
        days = 0
    return str(days)


def _days_sober_today(sobriety_date_value):
    sobriety_dt = _parse_dt(sobriety_date_value)
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

    submitted_dt = _parse_dt(submitted_at)
    if not submitted_dt:
        return "Submitted"

    if (datetime.utcnow().date() - submitted_dt.date()) <= timedelta(days=7):
        return f"Submitted {_format_dt(submitted_at, prefer_date_only=True)}"

    return "Not submitted this week"


def _load_resident_for_shelter(resident_id: int, shelter: str):
    return db_fetchone(
        _sql(
            f"""
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
                pe.exit_date,
                r.resident_code,
                r.birth_year,
                r.phone,
                r.email,
                r.emergency_contact_name,
                r.emergency_contact_relationship,
                r.emergency_contact_phone,
                r.medical_alerts,
                r.medical_notes,
                ia.sobriety_date,
                ia.days_sober_at_entry
            FROM residents r
            LEFT JOIN program_enrollments pe
                ON pe.resident_id = r.id
            LEFT JOIN intake_assessments ia
                ON ia.enrollment_id = pe.id
            WHERE r.id = %s AND {_shelter_equals_sql("r.shelter")}
            ORDER BY
                CASE
                    WHEN COALESCE(pe.program_status, '') = 'active' THEN 0
                    ELSE 1
                END,
                COALESCE(pe.entry_date, '') DESC,
                pe.id DESC
            LIMIT 1
            """,
            f"""
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
                pe.exit_date,
                r.resident_code,
                r.birth_year,
                r.phone,
                r.email,
                r.emergency_contact_name,
                r.emergency_contact_relationship,
                r.emergency_contact_phone,
                r.medical_alerts,
                r.medical_notes,
                ia.sobriety_date,
                ia.days_sober_at_entry
            FROM residents r
            LEFT JOIN program_enrollments pe
                ON pe.resident_id = r.id
            LEFT JOIN intake_assessments ia
                ON ia.enrollment_id = pe.id
            WHERE r.id = ? AND {_shelter_equals_sql("r.shelter")}
            ORDER BY
                CASE
                    WHEN COALESCE(pe.program_status, '') = 'active' THEN 0
                    ELSE 1
                END,
                COALESCE(pe.entry_date, '') DESC,
                pe.id DESC
            LIMIT 1
            """,
        ),
        (resident_id, shelter),
    )


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
    return db_fetchone(
        _sql(
            f"""
            SELECT
                r.id,
                pe.id AS enrollment_id
            FROM residents r
            LEFT JOIN program_enrollments pe
                ON pe.resident_id = r.id
            WHERE r.id = %s AND {_shelter_equals_sql("r.shelter")}
            ORDER BY
                CASE
                    WHEN COALESCE(pe.program_status, '') = 'active' THEN 0
                    ELSE 1
                END,
                COALESCE(pe.entry_date, '') DESC,
                pe.id DESC
            LIMIT 1
            """,
            f"""
            SELECT
                r.id,
                pe.id AS enrollment_id
            FROM residents r
            LEFT JOIN program_enrollments pe
                ON pe.resident_id = r.id
            WHERE r.id = ? AND {_shelter_equals_sql("r.shelter")}
            ORDER BY
                CASE
                    WHEN COALESCE(pe.program_status, '') = 'active' THEN 0
                    ELSE 1
                END,
                COALESCE(pe.entry_date, '') DESC,
                pe.id DESC
            LIMIT 1
            """,
        ),
        (resident_id, shelter),
    )


def _load_enrollment_context_for_shelter(resident_id: int, shelter: str) -> dict[str, object]:
    resident = _resident_enrollment_for_shelter(resident_id, shelter)
    enrollment_id = _row_value(resident, "enrollment_id", 1) if resident else None

    return {
        "resident": resident,
        "enrollment_id": enrollment_id,
    }


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
                    pe.entry_date AS event_time,
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
                    pe.entry_date AS event_time,
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


def _normalize_timeline(rows):
    items = []

    for row in rows or []:
        raw_time = _row_value(row, "event_time", 0)
        items.append(
            {
                "event_time": raw_time,
                "event_time_display": _format_dt(raw_time),
                "event_time_only": _format_time_only(raw_time),
                "event_type": _row_value(row, "event_type", 1, "activity"),
                "title": _row_value(row, "title", 2, "Activity"),
                "detail": _row_value(row, "detail", 3, "—"),
            }
        )

    return items


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
        next_appointment = _format_dt(appointment_date)
    else:
        next_appointment = "None scheduled"

    return {
        "program_status": str(program_status).replace("_", " ").title(),
        "goal_count": str(active_goal_count),
        "next_appointment": next_appointment,
        "compliance_status": _compliance_snapshot_text(compliance),
        "days_in_program": _days_in_program(entry_date),
    }


def _coerce_calendar_view(value: str | None) -> str:
    view = (value or "").strip().lower()
    if view in {"month", "week", "day"}:
        return view
    return "month"


def _parse_anchor_date(value: str | None) -> date:
    text = (value or "").strip()
    if text:
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            pass
    return datetime.utcnow().date()


def _start_of_week(value: date) -> date:
    offset = (value.weekday() + 1) % 7
    return value - timedelta(days=offset)


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    return date(year, month, 1)


def _event_type_theme(event_type: str) -> dict[str, str]:
    themes = {
        "enrollment_started": {
            "badge_class": "theme-blue",
            "label": "Enrollment",
        },
        "goal_created": {
            "badge_class": "theme-green",
            "label": "Goal",
        },
        "goal_completed": {
            "badge_class": "theme-green-dark",
            "label": "Completed Goal",
        },
        "case_note": {
            "badge_class": "theme-slate",
            "label": "Case Note",
        },
        "compliance_submitted": {
            "badge_class": "theme-amber",
            "label": "Compliance",
        },
        "appointment_scheduled": {
            "badge_class": "theme-purple",
            "label": "Scheduled",
        },
        "appointment_due": {
            "badge_class": "theme-rose",
            "label": "Appointment",
        },
    }
    return themes.get(
        event_type,
        {
            "badge_class": "theme-slate",
            "label": "Activity",
        },
    )


def _prepare_calendar_events(timeline):
    prepared = []

    for item in timeline or []:
        event_dt = _parse_dt(item.get("event_time"))
        if not event_dt:
            continue

        theme = _event_type_theme(item.get("event_type", "activity"))

        prepared.append(
            {
                **item,
                "event_dt": event_dt,
                "event_date": event_dt.date(),
                "time_label": item.get("event_time_only") or "All day",
                "badge_class": theme["badge_class"],
                "type_label": theme["label"],
            }
        )

    prepared.sort(
        key=lambda entry: (
            entry["event_date"],
            entry["event_dt"].time(),
            entry.get("title", ""),
        )
    )

    return prepared


def _build_calendar_context(timeline, selected_view: str, anchor: date):
    events = _prepare_calendar_events(timeline)
    events_by_date: dict[date, list[dict]] = {}

    for event in events:
        events_by_date.setdefault(event["event_date"], []).append(event)

    today = datetime.utcnow().date()
    month_names = [
        (1, "January"),
        (2, "February"),
        (3, "March"),
        (4, "April"),
        (5, "May"),
        (6, "June"),
        (7, "July"),
        (8, "August"),
        (9, "September"),
        (10, "October"),
        (11, "November"),
        (12, "December"),
    ]
    year_options = list(range(anchor.year - 3, anchor.year + 4))
    weekday_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    calendar = {
        "view": selected_view,
        "anchor": anchor.isoformat(),
        "anchor_date": anchor,
        "label": "",
        "prev_anchor": anchor.isoformat(),
        "next_anchor": anchor.isoformat(),
        "weekday_names": weekday_names,
        "month_names": month_names,
        "year_options": year_options,
        "selected_month": anchor.month,
        "selected_year": anchor.year,
        "month_days": [],
        "week_days": [],
        "day_events": [],
        "today_iso": today.isoformat(),
    }

    if selected_view == "month":
        month_start = date(anchor.year, anchor.month, 1)
        start_offset = (month_start.weekday() + 1) % 7
        grid_start = month_start - timedelta(days=start_offset)

        month_days = []
        for i in range(42):
            current_day = grid_start + timedelta(days=i)
            month_days.append(
                {
                    "date": current_day,
                    "date_iso": current_day.isoformat(),
                    "day_number": current_day.day,
                    "is_current_month": current_day.month == anchor.month,
                    "is_today": current_day == today,
                    "events": events_by_date.get(current_day, []),
                }
            )

        calendar["label"] = anchor.strftime("%B %Y")
        calendar["prev_anchor"] = _add_months(month_start, -1).isoformat()
        calendar["next_anchor"] = _add_months(month_start, 1).isoformat()
        calendar["month_days"] = month_days
        return calendar

    if selected_view == "week":
        week_start = _start_of_week(anchor)
        week_days = []

        for i in range(7):
            current_day = week_start + timedelta(days=i)
            week_days.append(
                {
                    "date": current_day,
                    "date_iso": current_day.isoformat(),
                    "day_name": current_day.strftime("%A"),
                    "short_day_name": current_day.strftime("%a"),
                    "day_number": current_day.day,
                    "month_name": current_day.strftime("%b"),
                    "is_today": current_day == today,
                    "events": events_by_date.get(current_day, []),
                }
            )

        week_end = week_start + timedelta(days=6)
        calendar["label"] = f"Week of {week_start.strftime('%b')} {week_start.day}, {week_start.year}"
        calendar["prev_anchor"] = (anchor - timedelta(days=7)).isoformat()
        calendar["next_anchor"] = (anchor + timedelta(days=7)).isoformat()
        calendar["week_days"] = week_days
        calendar["week_range_label"] = f"{week_start.strftime('%b')} {week_start.day} to {week_end.strftime('%b')} {week_end.day}, {week_end.year}"
        return calendar

    current_day = anchor
    calendar["label"] = f"{current_day.strftime('%A')}, {current_day.strftime('%B')} {current_day.day}, {current_day.year}"
    calendar["prev_anchor"] = (current_day - timedelta(days=1)).isoformat()
    calendar["next_anchor"] = (current_day + timedelta(days=1)).isoformat()
    calendar["day_events"] = events_by_date.get(current_day, [])
    calendar["day_date_iso"] = current_day.isoformat()
    return calendar


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

    selected_view = _coerce_calendar_view(request.args.get("view"))
    anchor_date = _parse_anchor_date(request.args.get("anchor"))
    empty_calendar = _build_calendar_context([], selected_view, anchor_date)

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
        timeline = _normalize_timeline(_load_timeline(enrollment_id))
        snapshot = {
            "program_status": str(_row_value(resident, "program_status", 7, "—") or "—").replace("_", " ").title(),
            "days_in_program": _days_in_program(_row_value(resident, "entry_date", 8)),
        }
        calendar = _build_calendar_context(timeline, selected_view, anchor_date)

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

    existing = db_fetchone(
        _sql(
            """
            SELECT
                id
            FROM program_enrollments
            WHERE resident_id = %s AND program_status = %s
            LIMIT 1
            """,
            """
            SELECT
                id
            FROM program_enrollments
            WHERE resident_id = ? AND program_status = ?
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
