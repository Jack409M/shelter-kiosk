from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from flask import g

from core.db import db_fetchall
from core.helpers import utcnow_iso
from core.pass_rules import pass_type_label
from routes.attendance_parts.helpers import to_local

CHICAGO_TZ = ZoneInfo("America/Chicago")


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _end_of_day_utc_naive(date_text: str | None) -> str | None:
    raw = _clean_text(date_text)
    if not raw:
        return None

    try:
        local_dt = datetime.combine(
            datetime.fromisoformat(raw).date(),
            time(hour=23, minute=59, second=59),
            tzinfo=CHICAGO_TZ,
        )
    except ValueError:
        return None

    return local_dt.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def _hydrate_pass_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)

    item["start_at_local"] = to_local(item.get("start_at"))
    item["end_at_local"] = to_local(item.get("end_at"))
    item["created_at_local"] = to_local(item.get("created_at"))
    item["approved_at_local"] = to_local(item.get("approved_at"))
    item["pass_type_label"] = pass_type_label(item.get("pass_type"))

    end_at_text = _clean_text(item.get("end_at"))
    expected_back_iso = end_at_text if end_at_text else _end_of_day_utc_naive(item.get("end_date"))

    item["expected_back_at"] = expected_back_iso
    item["expected_back_local"] = to_local(expected_back_iso)

    return item


def _hydrate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_hydrate_pass_row(row) for row in rows]


def fetch_pending_pass_rows(shelter: str) -> list[dict[str, Any]]:
    rows = db_fetchall(
        _sql(
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
            """,
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
            """,
        ),
        (shelter,),
    )

    return _hydrate_rows(rows)


def fetch_approved_pass_rows(shelter: str) -> list[dict[str, Any]]:
    rows = db_fetchall(
        _sql(
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
            """,
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
            """,
        ),
        (shelter,),
    )

    return _hydrate_rows(rows)


def fetch_current_pass_rows(shelter: str) -> list[dict[str, Any]]:
    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    rows = db_fetchall(
        _sql(
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
            """,
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
            """,
        ),
        (shelter, now_iso, now_iso, today_iso, today_iso),
    )

    return _hydrate_rows(rows)
