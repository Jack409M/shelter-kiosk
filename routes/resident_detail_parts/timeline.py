from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from core.db import db_fetchall


def parse_dt(value):
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


def is_date_only(value) -> bool:
    text = str(value or "").strip()
    return bool(text) and "T" not in text and ":" not in text and len(text) <= 10


def format_dt(value, *, prefer_date_only: bool = False) -> str:
    if value in (None, ""):
        return "—"

    dt = parse_dt(value)
    if not dt:
        return str(value)

    date_text = f"{dt.strftime('%b')} {dt.day}, {dt.year}"

    if prefer_date_only or is_date_only(value):
        return date_text

    time_text = dt.strftime("%I:%M %p").lstrip("0")
    return f"{date_text} {time_text}"


def format_time_only(value) -> str:
    if value in (None, ""):
        return ""

    dt = parse_dt(value)
    if not dt:
        return ""

    if is_date_only(value):
        return "All day"

    return dt.strftime("%I:%M %p").lstrip("0")


def normalize_timeline(rows):
    items = []

    for row in rows or []:
        raw_time = row.get("event_time") if isinstance(row, dict) else row[0]
        items.append(
            {
                "event_time": raw_time,
                "event_time_display": format_dt(raw_time),
                "event_time_only": format_time_only(raw_time),
                "event_type": (
                    (row.get("event_type") if isinstance(row, dict) else row[1]) or "activity"
                ),
                "title": ((row.get("title") if isinstance(row, dict) else row[2]) or "Activity"),
                "detail": ((row.get("detail") if isinstance(row, dict) else row[3]) or "—"),
            }
        )

    return items


def load_timeline(enrollment_id: int, sql_selector):
    return db_fetchall(
        sql_selector(
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
        ),
    )


def coerce_calendar_view(value: str | None) -> str:
    view = (value or "").strip().lower()
    if view in {"month", "week", "day"}:
        return view
    return "month"


def parse_anchor_date(value: str | None) -> date:
    text = (value or "").strip()
    if text:
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            pass
    return datetime.now(UTC).date()


def start_of_week(value: date) -> date:
    offset = (value.weekday() + 1) % 7
    return value - timedelta(days=offset)


def add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    return date(year, month, 1)


def event_type_theme(event_type: str) -> dict[str, str]:
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


def prepare_calendar_events(timeline):
    prepared = []

    for item in timeline or []:
        event_dt = parse_dt(item.get("event_time"))
        if not event_dt:
            continue

        theme = event_type_theme(item.get("event_type", "activity"))

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


def build_calendar_context(timeline, selected_view: str, anchor: date):
    events = prepare_calendar_events(timeline)
    events_by_date: dict[date, list[dict]] = {}

    for event in events:
        events_by_date.setdefault(event["event_date"], []).append(event)

    today = datetime.now(UTC).date()
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
        calendar["prev_anchor"] = add_months(month_start, -1).isoformat()
        calendar["next_anchor"] = add_months(month_start, 1).isoformat()
        calendar["month_days"] = month_days
        return calendar

    if selected_view == "week":
        week_start = start_of_week(anchor)
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
        calendar["label"] = (
            f"Week of {week_start.strftime('%b')} {week_start.day}, {week_start.year}"
        )
        calendar["prev_anchor"] = (anchor - timedelta(days=7)).isoformat()
        calendar["next_anchor"] = (anchor + timedelta(days=7)).isoformat()
        calendar["week_days"] = week_days
        calendar["week_range_label"] = (
            f"{week_start.strftime('%b')} {week_start.day} to {week_end.strftime('%b')} {week_end.day}, {week_end.year}"
        )
        return calendar

    current_day = anchor
    calendar["label"] = (
        f"{current_day.strftime('%A')}, {current_day.strftime('%B')} {current_day.day}, {current_day.year}"
    )
    calendar["prev_anchor"] = (current_day - timedelta(days=1)).isoformat()
    calendar["next_anchor"] = (current_day + timedelta(days=1)).isoformat()
    calendar["day_events"] = events_by_date.get(current_day, [])
    calendar["day_date_iso"] = current_day.isoformat()
    return calendar
