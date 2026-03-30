from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import g, session

from core.db import db_execute
from core.helpers import utcnow_iso


def parse_dt(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


def can_manage_passes() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def complete_active_passes(resident_id: int, shelter: str) -> None:
    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    db_execute(
        """
        UPDATE resident_passes
        SET status = %s,
            updated_at = %s
        WHERE resident_id = %s
          AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
          AND status = %s
          AND (
                (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at <= %s)
             OR (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= %s AND end_date >= %s)
          )
        """
        if g.get("db_kind") == "pg"
        else """
        UPDATE resident_passes
        SET status = ?,
            updated_at = ?
        WHERE resident_id = ?
          AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
          AND status = ?
          AND (
                (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at <= ?)
             OR (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= ? AND end_date >= ?)
          )
        """,
        ("completed", now_iso, resident_id, shelter, "approved", now_iso, today_iso, today_iso),
    )


def to_local(dt_iso):
    if not dt_iso:
        return None
    try:
        dt = datetime.fromisoformat(dt_iso).replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("America/Chicago"))
    except Exception:
        return None
