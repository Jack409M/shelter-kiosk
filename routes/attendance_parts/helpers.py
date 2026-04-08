from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import session

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso

CHICAGO_TZ = ZoneInfo("America/Chicago")


def parse_dt(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


def can_manage_passes() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _expected_back_utc_for_pass(end_at: str | None, end_date: str | None) -> datetime | None:
    raw_end_at = (end_at or "").strip()
    if raw_end_at:
        try:
            return datetime.fromisoformat(raw_end_at)
        except Exception:
            return None

    raw_end_date = (end_date or "").strip()
    if raw_end_date:
        try:
            local_dt = datetime.combine(
                datetime.fromisoformat(raw_end_date).date(),
                time(hour=23, minute=59, second=59),
                tzinfo=CHICAGO_TZ,
            )
            return local_dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return None

    return None


def _delete_after_from_check_in(
    check_in_iso: str,
    end_at: str | None,
    end_date: str | None,
) -> str:
    check_in_dt = datetime.fromisoformat(check_in_iso)
    expected_back_dt = _expected_back_utc_for_pass(end_at, end_date)

    if expected_back_dt is None:
        later_dt = check_in_dt
    else:
        later_dt = check_in_dt if check_in_dt >= expected_back_dt else expected_back_dt

    return (later_dt + timedelta(hours=48)).isoformat(timespec="seconds")


def complete_active_passes(resident_id: int, shelter: str) -> None:
    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    active_rows = db_fetchall(
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
        """,
        (resident_id, shelter, "approved", now_iso, today_iso, today_iso),
    )

    for row in active_rows:
        delete_after_at = _delete_after_from_check_in(
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
            """,
            ("completed", now_iso, delete_after_at, row["id"]),
        )


def to_local(dt_iso):
    if not dt_iso:
        return None
    try:
        dt = datetime.fromisoformat(dt_iso).replace(tzinfo=timezone.utc)
        return dt.astimezone(CHICAGO_TZ)
    except Exception:
        return None
