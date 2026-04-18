from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Blueprint, current_app, g, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.db import db_fetchall, db_fetchone, get_db
from core.pass_retention import run_pass_retention_cleanup_for_shelter
from core.pass_rules import CHICAGO_TZ, pass_type_label
from core.helpers import utcnow_iso
from routes.attendance_parts.helpers import to_local

resident_portal = Blueprint("resident_portal", __name__)


def _clear_resident_session() -> None:
    session.clear()


def _resident_signin_redirect():
    return redirect(url_for("resident_requests.resident_signin", next=request.path))


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _safe_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


# 🔴 NEW — load real program level
def _load_resident_level(resident_id: int | None) -> int:
    if resident_id is None:
        return 0

    row = db_fetchone(
        _sql(
            """
            SELECT program_level
            FROM residents
            WHERE id = %s
            """,
            """
            SELECT program_level
            FROM residents
            WHERE id = ?
            """,
        ),
        (resident_id,),
    )

    if not row:
        return 0

    try:
        return int(row.get("program_level") or 0)
    except Exception:
        return 0


def _hydrate_pass_item(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["pass_type_label"] = pass_type_label(item.get("pass_type"))
    item["start_at_local"] = to_local(item.get("start_at"))
    item["end_at_local"] = to_local(item.get("end_at"))
    item["created_at_local"] = to_local(item.get("created_at"))
    item["approved_at_local"] = to_local(item.get("approved_at"))
    item["is_active"] = _pass_item_is_active(item)
    return item


def _pass_item_is_active(item: dict[str, Any]) -> bool:
    if _clean_text(item.get("status")).lower() != "approved":
        return False

    now_iso = utcnow_iso()
    today_iso = now_iso[:10]
    start_at = _clean_text(item.get("start_at"))
    end_at = _clean_text(item.get("end_at"))
    start_date = _clean_text(item.get("start_date"))
    end_date = _clean_text(item.get("end_date"))

    if start_at and end_at:
        return start_at <= now_iso <= end_at

    if start_date and end_date:
        return start_date <= today_iso <= end_date

    return False


def _load_recent_pass_items(resident_id: int | None, shelter: str) -> list[dict[str, Any]]:
    if resident_id is None or not shelter:
        return []

    rows = db_fetchall(
        _sql(
            """
            SELECT
                rp.id,
                rp.pass_type,
                rp.status,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.resident_notes,
                rp.staff_notes,
                rp.created_at,
                rp.approved_at,
                rprd.request_date
            FROM resident_passes rp
            LEFT JOIN resident_pass_request_details rprd
              ON rprd.pass_id = rp.id
            WHERE rp.resident_id = %s
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
            ORDER BY rp.created_at DESC, rp.id DESC
            LIMIT 5
            """,
            """
            SELECT
                rp.id,
                rp.pass_type,
                rp.status,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.resident_notes,
                rp.staff_notes,
                rp.created_at,
                rp.approved_at,
                rprd.request_date
            FROM resident_passes rp
            LEFT JOIN resident_pass_request_details rprd
              ON rprd.pass_id = rp.id
            WHERE rp.resident_id = ?
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
            ORDER BY rp.created_at DESC, rp.id DESC
            LIMIT 5
            """,
        ),
        (resident_id, shelter),
    )

    return [_hydrate_pass_item(row) for row in rows]


def _load_active_pass_item(resident_id: int | None, shelter: str) -> dict[str, Any] | None:
    if resident_id is None or not shelter:
        return None

    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    rows = db_fetchall(
        _sql(
            """
            SELECT
                rp.id,
                rp.pass_type,
                rp.status,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.resident_notes,
                rp.staff_notes,
                rp.created_at,
                rp.approved_at
            FROM resident_passes rp
            WHERE rp.resident_id = %s
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
              AND rp.status = 'approved'
              AND (
                    (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= %s AND rp.end_at >= %s)
                 OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= %s AND rp.end_date >= %s)
              )
            ORDER BY rp.approved_at DESC, rp.created_at DESC, rp.id DESC
            LIMIT 1
            """,
            """
            SELECT
                rp.id,
                rp.pass_type,
                rp.status,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.resident_notes,
                rp.staff_notes,
                rp.created_at,
                rp.approved_at
            FROM resident_passes rp
            WHERE rp.resident_id = ?
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
              AND rp.status = 'approved'
              AND (
                    (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= ? AND rp.end_at >= ?)
                 OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= ? AND rp.end_date >= ?)
              )
            ORDER BY rp.approved_at DESC, rp.created_at DESC, rp.id DESC
            LIMIT 1
            """,
        ),
        (resident_id, shelter, now_iso, now_iso, today_iso, today_iso),
    )

    if not rows:
        return None

    return _hydrate_pass_item(rows[0])


# 🔴 NEW ROUTE — Level 5 Hours Page
@resident_portal.route("/resident/hours", methods=["GET", "POST"])
@require_resident
def resident_hours():
    try:
        resident_id = _safe_int(session.get("resident_id"))
        shelter = _clean_text(session.get("resident_shelter"))

        get_db()

        level = _load_resident_level(resident_id)

        # 🔴 Gate Level 5+
        if level < 5:
            return redirect(url_for("resident_portal.home"))

        if request.method == "POST":
            now_iso = utcnow_iso()

            # simple 8 hour submission
            db_execute(
                _sql(
                    """
                    INSERT INTO attendance_events (
                        resident_id,
                        shelter,
                        event_type,
                        event_time,
                        staff_user_id,
                        note,
                        obligation_start_time,
                        obligation_end_time,
                        meeting_count,
                        is_recovery_meeting
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    """
                    INSERT INTO attendance_events (
                        resident_id,
                        shelter,
                        event_type,
                        event_time,
                        staff_user_id,
                        note,
                        obligation_start_time,
                        obligation_end_time,
                        meeting_count,
                        is_recovery_meeting
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                ),
                (
                    resident_id,
                    shelter,
                    "obligation_complete",
                    now_iso,
                    None,
                    "Resident submitted 8 hours",
                    None,
                    None,
                    0,
                    0,
                ),
            )

            return redirect(url_for("resident_portal.home"))

        return render_template("resident_hours.html")

    except Exception as exc:
        current_app.logger.exception("resident_hours_failed")
        _clear_resident_session()
        return _resident_signin_redirect()


@resident_portal.route("/resident/home")
@require_resident
def home():
    resident_id = None
    shelter = ""

    try:
        resident_id_raw = session.get("resident_id")
        resident_id = int(resident_id_raw) if resident_id_raw not in (None, "") else None
        shelter = str(session.get("resident_shelter") or "").strip()
        resident_identifier = str(session.get("resident_identifier") or "").strip()

        get_db()

        if shelter:
            run_pass_retention_cleanup_for_shelter(shelter)

        # 🔴 load level for template
        level = _load_resident_level(resident_id)

        pass_items = _load_recent_pass_items(resident_id, shelter)
        active_pass = _load_active_pass_item(resident_id, shelter)

        return render_template(
            "resident_home.html",
            pass_items=pass_items,
            active_pass=active_pass,
            resident_level=level,
        )

    except Exception as exc:
        current_app.logger.exception("resident_portal_home_failed")
        _clear_resident_session()
        return _resident_signin_redirect()
