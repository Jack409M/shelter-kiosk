from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from flask import g

from core.db import db_fetchall


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _parse_dateish(value: Any):
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value.date()

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass

    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def _days_since(value: Any) -> int | None:
    parsed = _parse_dateish(value)
    if not parsed:
        return None

    days = (datetime.now().date() - parsed).days
    if days < 0:
        days = 0
    return days


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _shelter_equals_sql(column_name: str) -> str:
    ph = _placeholder()
    return f"LOWER(TRIM(COALESCE({column_name}, ''))) = LOWER(TRIM({ph}))"


def _fetch_recovery_meeting_rows(
    resident_id: int,
    shelter: str,
    start_date: Any | None = None,
):
    ph = _placeholder()
    params: list[Any] = [resident_id, shelter]

    date_sql = ""
    if start_date:
        parsed_start = _parse_dateish(start_date)
        if parsed_start:
            date_sql = f" AND event_time >= {ph}"
            params.append(parsed_start.isoformat() + "T00:00:00")

    return db_fetchall(
        f"""
        SELECT
            id,
            event_time,
            destination,
            meeting_count,
            meeting_1,
            meeting_2,
            is_recovery_meeting
        FROM attendance_events
        WHERE resident_id = {ph}
          AND {_shelter_equals_sql("shelter")}
          AND event_type = 'check_out'
          AND COALESCE(is_recovery_meeting, 0) = 1
          {date_sql}
        ORDER BY event_time ASC, id ASC
        """,
        tuple(params),
    )


def _meeting_row_to_count(row: dict) -> int:
    stored_count = _safe_int(row.get("meeting_count"), 0)
    if stored_count > 0:
        return stored_count

    fallback = 0
    if (row.get("meeting_1") or "").strip():
        fallback += 1
    if (row.get("meeting_2") or "").strip():
        fallback += 1

    return fallback


def _week_start(d: datetime.date):
    return d - timedelta(days=d.weekday())


def calculate_meeting_progress(
    resident_id: int,
    shelter: str,
    program_start_date: Any | None,
    level_value: str | None = None,
) -> dict[str, Any]:
    rows = _fetch_recovery_meeting_rows(
        resident_id=resident_id,
        shelter=shelter,
        start_date=program_start_date,
    )

    today = datetime.now().date()
    current_week_start = _week_start(today)
    last_30_start = today - timedelta(days=29)
    last_90_start = today - timedelta(days=89)

    total_meetings = 0
    meetings_this_week = 0
    meetings_last_30_days = 0
    meetings_last_90_days = 0

    weekly_totals: dict[str, int] = {}

    for raw_row in rows or []:
        row = dict(raw_row) if not isinstance(raw_row, dict) else raw_row
        event_date = _parse_dateish(row.get("event_time"))
        if not event_date:
            continue

        meeting_count = _meeting_row_to_count(row)
        if meeting_count <= 0:
            continue

        total_meetings += meeting_count

        week_key = _week_start(event_date).isoformat()
        weekly_totals[week_key] = weekly_totals.get(week_key, 0) + meeting_count

        if event_date >= current_week_start:
            meetings_this_week += meeting_count

        if event_date >= last_30_start:
            meetings_last_30_days += meeting_count

        if event_date >= last_90_start:
            meetings_last_90_days += meeting_count

    days_in_program = _days_since(program_start_date)
    if days_in_program is None:
        days_in_program = 0

    expected_meetings_so_far = min(days_in_program, 90)
    pace_percent = 0.0
    if expected_meetings_so_far > 0:
        pace_percent = round((total_meetings / expected_meetings_so_far) * 100.0, 1)

    projected_90_day_total = 0
    if days_in_program > 0:
        projected_90_day_total = int(round((total_meetings / days_in_program) * 90))
    elif total_meetings > 0:
        projected_90_day_total = total_meetings

    meetings_remaining_to_90 = max(0, 90 - total_meetings)
    completed_90_in_90 = total_meetings >= 90

    level_num = _safe_int("".join(ch for ch in str(level_value or "") if ch.isdigit()), 0)

    required_weekly_meetings = None
    if level_num == 3:
        required_weekly_meetings = 6
    elif level_num == 4:
        required_weekly_meetings = 5

    weekly_requirement_met = None
    if required_weekly_meetings is not None:
        weekly_requirement_met = meetings_this_week >= required_weekly_meetings

    if completed_90_in_90:
        status_label = "90 in 90 Complete"
    elif expected_meetings_so_far == 0:
        status_label = "Not Started"
    elif pace_percent >= 100.0:
        status_label = "On Pace for 90 in 90"
    else:
        status_label = "Behind Pace for 90 in 90"

    weekly_rows = []
    for week_key in sorted(weekly_totals.keys(), reverse=True):
        weekly_rows.append(
            {
                "week_start": week_key,
                "meeting_count": weekly_totals[week_key],
            }
        )

    return {
        "total_meetings": total_meetings,
        "meetings_this_week": meetings_this_week,
        "meetings_last_30_days": meetings_last_30_days,
        "meetings_last_90_days": meetings_last_90_days,
        "days_in_program": days_in_program,
        "expected_meetings_so_far": expected_meetings_so_far,
        "pace_percent": pace_percent,
        "pace_percent_display": f"{pace_percent:.1f}%",
        "projected_90_day_total": projected_90_day_total,
        "meetings_remaining_to_90": meetings_remaining_to_90,
        "completed_90_in_90": completed_90_in_90,
        "completed_116_meetings": total_meetings >= 116,
        "completed_168_meetings": total_meetings >= 168,
        "required_weekly_meetings": required_weekly_meetings,
        "weekly_requirement_met": weekly_requirement_met,
        "status_label": status_label,
        "weekly_rows": weekly_rows,
        "has_meeting_data": total_meetings > 0,
    }
