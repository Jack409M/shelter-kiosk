from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import session

from core.db import db_execute
from core.helpers import utcnow_iso


CHICAGO_TZ = ZoneInfo("America/Chicago")


def parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt
    return dt.replace(tzinfo=None)


def can_manage_passes() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def to_local(dt_iso: str | None) -> datetime | None:
    if not dt_iso:
        return None

    try:
        dt = datetime.fromisoformat(str(dt_iso))
    except Exception:
        return None

    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(CHICAGO_TZ)
    except Exception:
        return None


def complete_active_passes(resident_id: int, shelter: str) -> None:
    from core.pass_retention import cleanup_deadline_from_expected_back

    rows = db_execute(
        """
        SELECT id, end_at, end_date
        FROM resident_passes
        WHERE resident_id = %s
          AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
          AND LOWER(TRIM(status)) = 'approved'
        """
        if session.get("db_kind") == "pg"
        else """
        SELECT id, end_at, end_date
        FROM resident_passes
        WHERE resident_id = ?
          AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
          AND LOWER(TRIM(status)) = 'approved'
        """,
        (resident_id, shelter),
    )

    now = utcnow_iso()

    for row in rows or []:
        delete_after = cleanup_deadline_from_expected_back(
            row.get("end_at"),
            row.get("end_date"),
        )

        db_execute(
            """
            UPDATE resident_passes
            SET status = %s,
                updated_at = %s,
                delete_after_at = %s
            WHERE id = %s
            """
            if session.get("db_kind") == "pg"
            else """
            UPDATE resident_passes
            SET status = ?,
                updated_at = ?,
                delete_after_at = ?
            WHERE id = ?
            """,
            ("completed", now, delete_after, row["id"]),
        )
