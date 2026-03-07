from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, render_template, session

from core.auth import require_login, require_shelter
from core.db import db_fetchall, db_fetchone
from core.helpers import fmt_time_only


attendance = Blueprint("attendance", __name__)


def _is_pg() -> bool:
    return bool(current_app.config.get("DATABASE_URL"))


def _get_value(row: Any, key: str, index: int, default: Any = "") -> Any:
    if not row:
        return default
    if isinstance(row, dict):
        value = row.get(key, default)
    else:
        value = row[index] if len(row) > index else default
    return default if value is None else value


@attendance.route("/staff/attendance")
@require_login
@require_shelter
def staff_attendance():
    shelter = session["shelter"]
    is_pg = _is_pg()

    residents_sql = (
        "SELECT * FROM residents WHERE shelter = %s AND is_active = TRUE ORDER BY last_name, first_name"
        if is_pg
        else "SELECT * FROM residents WHERE shelter = ? AND is_active = 1 ORDER BY last_name, first_name"
    )

    last_event_sql = (
        """
        SELECT event_type, event_time, expected_back_time, note
        FROM attendance_events
        WHERE resident_id = %s AND shelter = %s
        ORDER BY event_time DESC
        LIMIT 1
        """
        if is_pg
        else """
        SELECT event_type, event_time, expected_back_time, note
        FROM attendance_events
        WHERE resident_id = ? AND shelter = ?
        ORDER BY event_time DESC
        LIMIT 1
        """
    )

    last_checkout_sql = (
        """
        SELECT event_time, expected_back_time, note
        FROM attendance_events
        WHERE resident_id = %s AND shelter = %s AND event_type = %s
        ORDER BY event_time DESC
        LIMIT 1
        """
        if is_pg
        else """
        SELECT event_time, expected_back_time, note
        FROM attendance_events
        WHERE resident_id = ? AND shelter = ? AND event_type = ?
        ORDER BY event_time DESC
        LIMIT 1
        """
    )

    residents = db_fetchall(residents_sql, (shelter,))

    out_rows: list[dict[str, Any]] = []
    in_rows: list[dict[str, Any]] = []

    for r in residents:
        rid = int(_get_value(r, "id", 0, 0))
        first = _get_value(r, "first_name", 4, "")
        last = _get_value(r, "last_name", 5, "")

        last_event = db_fetchone(last_event_sql, (rid, shelter))
        last_event_type = _get_value(last_event, "event_type", 0, "")

        last_checkout = db_fetchone(last_checkout_sql, (rid, shelter, "check_out"))
        checkout_time = _get_value(last_checkout, "event_time", 0, "")
        expected_back_time = _get_value(last_checkout, "expected_back_time", 1, "")
        checkout_note = _get_value(last_checkout, "note", 2, "")

        is_out = last_event_type == "check_out"

        row = {
            "resident_id": rid,
            "first_name": first,
            "last_name": last,
            "name": f"{last}, {first}",
            "checked_out_at": checkout_time,
            "expected_back_at": expected_back_time,
            "is_out": is_out,
            "note": checkout_note,
        }

        if is_out:
            out_rows.append(row)
        else:
            in_rows.append(row)

    out_rows.sort(key=lambda x: (x["last_name"].lower(), x["first_name"].lower()))
    in_rows.sort(key=lambda x: (x["last_name"].lower(), x["first_name"].lower()))

    return render_template(
        "staff_attendance.html",
        out_rows=out_rows,
        in_rows=in_rows,
        fmt_time=fmt_time_only,
        shelter=shelter,
    )

from flask import redirect, url_for
from core.db import db_execute
from core.helpers import utcnow_iso
from core.audit import log_action


@attendance.route("/staff/attendance/<int:resident_id>/check-in", methods=["POST"])
@require_login
@require_shelter
def staff_attendance_check_in(resident_id: int):
    shelter = session["shelter"]

    sql = (
        """
        INSERT INTO attendance_events (resident_id, event_type, event_time, shelter)
        VALUES (%s, %s, %s, %s)
        """
        if current_app.config.get("DATABASE_URL")
        else """
        INSERT INTO attendance_events (resident_id, event_type, event_time, shelter)
        VALUES (?, ?, ?, ?)
        """
    )

    db_execute(sql, (resident_id, "check_in", utcnow_iso(), shelter))

    log_action(
        "attendance_check_in",
        resident_id=resident_id,
        shelter=shelter,
    )

    return redirect(url_for("attendance.staff_attendance"))
