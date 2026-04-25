from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from flask import current_app

import routes.resident_portal as portal
from core.access import require_resident
from core.db import db_fetchone
from core.pass_rules import CHICAGO_TZ
from core.resident_portal_service import get_today_chores
from routes.resident_portal import resident_portal
from routes.resident_portal_parts.helpers import (
    _clear_resident_session,
    _load_active_pass_item,
    _load_recent_notification_items,
    _load_recent_transport_items,
    _load_resident_program_level,
    _prepare_resident_request_context,
    _resident_signin_redirect,
    _sql,
)


def _empty_weekly_activity_summary() -> dict[str, float | int]:
    return {"work_hours": 0.0, "productive_hours": 0.0, "meeting_count": 0}


def _load_weekly_activity_summary(resident_id: int | None, shelter: str) -> dict[str, float | int]:
    if resident_id is None or not shelter:
        return _empty_weekly_activity_summary()

    today = datetime.now(CHICAGO_TZ).date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    week_start_utc = datetime.combine(week_start, time.min, tzinfo=CHICAGO_TZ).astimezone(UTC).replace(tzinfo=None)
    week_end_utc = datetime.combine(week_end, time.min, tzinfo=CHICAGO_TZ).astimezone(UTC).replace(tzinfo=None)

    try:
        row = db_fetchone(
            _sql(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN COALESCE(c.counts_as_work_hours, FALSE) = TRUE THEN COALESCE(a.logged_hours, 0) ELSE 0 END), 0) AS work_hours,
                    COALESCE(SUM(CASE WHEN COALESCE(c.counts_as_productive_hours, FALSE) = TRUE THEN COALESCE(a.logged_hours, 0) ELSE 0 END), 0) AS productive_logged_hours,
                    COALESCE(SUM(COALESCE(a.meeting_count, 0)), 0) AS meeting_count
                FROM attendance_events a
                LEFT JOIN kiosk_activity_categories c
                  ON LOWER(TRIM(c.shelter)) = LOWER(TRIM(a.shelter))
                 AND LOWER(TRIM(c.activity_label)) = LOWER(TRIM(a.destination))
                WHERE a.resident_id = %s
                  AND LOWER(TRIM(a.shelter)) = LOWER(TRIM(%s))
                  AND a.event_type = 'resident_daily_log'
                  AND a.event_time >= %s
                  AND a.event_time < %s
                """,
                """
                SELECT
                    COALESCE(SUM(CASE WHEN COALESCE(c.counts_as_work_hours, 0) = 1 THEN COALESCE(a.logged_hours, 0) ELSE 0 END), 0) AS work_hours,
                    COALESCE(SUM(CASE WHEN COALESCE(c.counts_as_productive_hours, 0) = 1 THEN COALESCE(a.logged_hours, 0) ELSE 0 END), 0) AS productive_logged_hours,
                    COALESCE(SUM(COALESCE(a.meeting_count, 0)), 0) AS meeting_count
                FROM attendance_events a
                LEFT JOIN kiosk_activity_categories c
                  ON LOWER(TRIM(c.shelter)) = LOWER(TRIM(a.shelter))
                 AND LOWER(TRIM(c.activity_label)) = LOWER(TRIM(a.destination))
                WHERE a.resident_id = ?
                  AND LOWER(TRIM(a.shelter)) = LOWER(TRIM(?))
                  AND a.event_type = 'resident_daily_log'
                  AND a.event_time >= ?
                  AND a.event_time < ?
                """,
            ),
            (
                resident_id,
                shelter,
                week_start_utc.isoformat(timespec="seconds"),
                week_end_utc.isoformat(timespec="seconds"),
            ),
        )
    except Exception:
        current_app.logger.info(
            "weekly_activity_summary_unavailable resident_id=%s shelter=%s",
            resident_id,
            shelter,
        )
        return _empty_weekly_activity_summary()

    work_hours = float((row or {}).get("work_hours") or 0)
    productive_logged_hours = float((row or {}).get("productive_logged_hours") or 0)
    meeting_count = int((row or {}).get("meeting_count") or 0)

    return {
        "work_hours": round(work_hours, 2),
        "productive_hours": round(productive_logged_hours + meeting_count, 2),
        "meeting_count": meeting_count,
    }


@resident_portal.route("/resident/portal")
@resident_portal.route("/resident/home")
@require_resident
def home():
    resident_id = None
    shelter = ""

    try:
        resident_id, shelter, resident_identifier = _prepare_resident_request_context()

        portal.get_db()
        portal.run_pass_retention_cleanup_for_shelter(shelter)

        resident_level = _load_resident_program_level(resident_id)
        weekly_activity_summary = _load_weekly_activity_summary(resident_id, shelter)

        pass_items = portal._load_recent_pass_items(resident_id, shelter)

        active_pass = _load_active_pass_item(resident_id, shelter)
        notification_items = _load_recent_notification_items(resident_id, shelter)
        transport_items = _load_recent_transport_items(resident_identifier, shelter)
        chores = get_today_chores(resident_id) if resident_id is not None else []

        return portal.render_template(
            "resident_home.html",
            recent_items=pass_items,
            pass_items=pass_items,
            active_pass=active_pass,
            notification_items=notification_items,
            transport_items=transport_items,
            chores=chores,
            resident_level=resident_level,
            weekly_activity_summary=weekly_activity_summary,
        )

    except Exception as exc:
        current_app.logger.exception(
            "resident_portal_home_failed resident_id=%s shelter=%s exception_type=%s",
            resident_id if resident_id is not None else "unknown",
            shelter or "unknown",
            type(exc).__name__,
        )
        _clear_resident_session()
        return _resident_signin_redirect()
