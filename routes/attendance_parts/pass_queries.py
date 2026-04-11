from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from flask import g

from core.db import db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from routes.attendance_parts.helpers import to_local

CHICAGO_TZ = ZoneInfo("America/Chicago")


def _end_of_day_utc_naive(date_text: str | None) -> str | None:
    raw = (date_text or "").strip()
    if not raw:
        return None
    try:
        local_dt = datetime.combine(
            datetime.fromisoformat(raw).date(),
            time(hour=23, minute=59, second=59),
            tzinfo=CHICAGO_TZ,
        )
        return (
            local_dt.astimezone(timezone.utc)
            .replace(tzinfo=None)
            .isoformat(timespec="seconds")
        )
    except Exception:
        return None


def _hydrate_pass_row(item: dict) -> dict:
    item["start_at_local"] = to_local(item.get("start_at"))
    item["end_at_local"] = to_local(item.get("end_at"))
    item["created_at_local"] = to_local(item.get("created_at"))
    item["approved_at_local"] = to_local(item.get("approved_at"))

    if item.get("end_at"):
        expected_back_iso = str(item.get("end_at") or "").strip()
    else:
        expected_back_iso = _end_of_day_utc_naive(item.get("end_date"))

    item["expected_back_at"] = expected_back_iso
    item["expected_back_local"] = to_local(expected_back_iso)

    return item


def fetch_pending_pass_rows(shelter: str) -> list[dict]:
    sql = (
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
            rp.created_at
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'pending'
        AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
        ORDER BY rp.created_at ASC
        """
        if g.get("db_kind") == "pg"
        else
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
            rp.created_at
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'pending'
        AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
        ORDER BY rp.created_at ASC
        """
    )

    rows = db_fetchall(sql, (shelter,))
    return [_hydrate_pass_row(dict(r)) for r in rows]


def fetch_approved_pass_rows(shelter: str) -> list[dict]:
    sql = (
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
            rp.approved_at
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'approved'
        AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
        ORDER BY rp.approved_at ASC, rp.created_at ASC
        """
        if g.get("db_kind") == "pg"
        else
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
            rp.approved_at
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'approved'
        AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
        ORDER BY rp.approved_at ASC, rp.created_at ASC
        """
    )

    rows = db_fetchall(sql, (shelter,))
    return [_hydrate_pass_row(dict(r)) for r in rows]


def fetch_current_pass_rows(shelter: str) -> list[dict]:
    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    sql = (
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.shelter,
            rp.pass_type,
            rp.status,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            rp.destination,
            rp.reason,
            rp.created_at,
            rp.approved_at,
            r.first_name,
            r.last_name
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'approved'
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
          AND (
                (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= %s AND rp.end_at >= %s)
             OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= %s AND rp.end_date >= %s)
          )
        ORDER BY rp.created_at ASC
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.shelter,
            rp.pass_type,
            rp.status,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            rp.destination,
            rp.reason,
            rp.created_at,
            rp.approved_at,
            r.first_name,
            r.last_name
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'approved'
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
          AND (
                (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= ? AND rp.end_at >= ?)
             OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= ? AND rp.end_date >= ?)
          )
        ORDER BY rp.created_at ASC
        """
    )

    rows = db_fetchall(
        sql,
        (shelter, now_iso, now_iso, today_iso, today_iso),
    )

    return [_hydrate_pass_row(dict(r)) for r in rows]
