from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import g, session

from core.db import db_execute
from core.helpers import utcnow_iso


def parse_dt(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


def can_manage_passes() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _later_delete_after_at(
    check_in_iso: str,
    end_at: str | None,
    end_date: str | None,
) -> str:
    check_in_dt = datetime.fromisoformat(check_in_iso)

    expected_dt = check_in_dt
    if end_at:
        try:
            expected_dt = datetime.fromisoformat(end_at)
        except Exception:
            expected_dt = check_in_dt
    elif end_date:
        try:
            local_end_of_day = datetime.combine(
                datetime.fromisoformat(end_date).date(),
                datetime.max.time().replace(microsecond=0),
                tzinfo=ZoneInfo("America/Chicago"),
            )
            expected_dt = (
                local_end_of_day.astimezone(timezone.utc)
                .replace(tzinfo=None)
            )
        except Exception:
            expected_dt = check_in_dt

    later_dt = check_in_dt if check_in_dt >= expected_dt else expected_dt
    return (later_dt + timedelta(hours=48)).isoformat(timespec="seconds")


def complete_active_passes(resident_id: int, shelter: str) -> None:
    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    active_rows = db_execute(
        """
        SELECT id, end_at, end_date
        FROM resident_passes
        WHERE resident_id = %s
          AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
          AND status = %s
          AND (
                (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at <= %s)
             OR (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= %s AND end_date >= %s)
          )
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT id, end_at, end_date
        FROM resident_passes
        WHERE resident_id = ?
          AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
          AND status = ?
          AND (
                (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at <= ?)
             OR (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= ? AND end_date >= ?)
          )
        """,
        (resident_id, shelter, "approved", now_iso, today_iso, today_iso),
        fetchall=True,
    ) or []

    for row in active_rows:
        delete_after_at = _later_delete_after_at(
            check_in_iso=now_iso,
            end_at=row.get("end_at"),
            end_date=row.get("end_date"),
        )

        db_execute(
            """
            UPDATE resident_passes
            SET status = %s,
                updated_at = %s,
                delete_after_at = %s
            WHERE id = %s
            """
            if g.get("db_kind") == "pg"
            else
            """
            UPDATE resident_passes
            SET status = ?,
                updated_at = ?,
                delete_after_at = ?
            WHERE id = ?
            """,
            ("completed", now_iso, delete_after_at, row["id"]),
        )


def to_local(dt_iso):
    if not dt_iso:
        return None
    try:
        dt = datetime.fromisoformat(dt_iso).replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("America/Chicago"))
    except Exception:
        return None
