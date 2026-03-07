from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import fmt_dt, fmt_time_only, utcnow_iso


attendance = Blueprint("attendance", __name__)


def parse_dt(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


@attendance.route("/staff/attendance")
@require_login
@require_shelter
def staff_attendance():
    shelter = session["shelter"]

    residents = db_fetchall(
        "SELECT * FROM residents WHERE shelter = %s AND is_active = TRUE ORDER BY last_name, first_name"
        if current_app.config.get("DATABASE_URL")
        else "SELECT * FROM residents WHERE shelter = ? AND is_active = 1 ORDER BY last_name, first_name",
        (shelter,),
    )

    out_rows: list[dict[str, Any]] = []
    in_rows: list[dict[str, Any]] = []

    for r in residents:
        rid = int(r["id"] if isinstance(r, dict) else r[0])
        first = r["first_name"] if isinstance(r, dict) else r[4]
        last = r["last_name"] if isinstance(r, dict) else r[5]

        last_event = db_fetchone(
            """
            SELECT event_type, event_time, expected_back_time, note
            FROM attendance_events
            WHERE resident_id = %s AND shelter = %s
            ORDER BY event_time DESC
            LIMIT 1
            """
            if current_app.config.get("DATABASE_URL")
            else """
            SELECT event_type, event_time, expected_back_time, note
            FROM attendance_events
            WHERE resident_id = ? AND shelter = ?
            ORDER BY event_time DESC
            LIMIT 1
            """,
            (rid, shelter),
        )

        last_event_type = ""
        if last_event:
            last_event_type = last_event["event_type"] if isinstance(last_event, dict) else last_event[0]

        last_checkout = db_fetchone(
            """
            SELECT event_time, expected_back_time, note
            FROM attendance_events
            WHERE resident_id = %s AND shelter = %s AND event_type = %s
            ORDER BY event_time DESC
            LIMIT 1
            """
            if current_app.config.get("DATABASE_URL")
            else """
            SELECT event_time, expected_back_time, note
            FROM attendance_events
            WHERE resident_id = ? AND shelter = ? AND event_type = ?
            ORDER BY event_time DESC
            LIMIT 1
            """,
            (rid, shelter, "check_out"),
        )

        checkout_time = ""
        expected_back_time = ""
        checkout_note = ""

        if last_checkout:
            checkout_time = last_checkout["event_time"] if isinstance(last_checkout, dict) else last_checkout[0]
            expected_back_time = last_checkout["expected_back_time"] if isinstance(last_checkout, dict) else (last_checkout[1] or "")
            checkout_note = (last_checkout["note"] if isinstance(last_checkout, dict) else last_checkout[2]) or ""

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


@attendance.route("/staff/attendance/<int:resident_id>/check-in", methods=["POST"]) 
@require_login
@require_shelter
def staff_attendance_check_in(resident_id: int):
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]

    resident = db_fetchone(
        "SELECT id FROM residents WHERE id = %s AND shelter = %s AND is_active = TRUE"
        if current_app.config.get("DATABASE_URL")
        else "SELECT id FROM residents WHERE id = ? AND shelter = ? AND is_active = 1",
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    db_execute(
        """
        INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        if current_app.config.get("DATABASE_URL")
        else """
        INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (resident_id, shelter, "check_in", utcnow_iso(), staff_id, "Manual check in", None),
    )

    log_action("attendance", resident_id, shelter, staff_id, "check_in", "Manual check in")
    flash("Resident checked in.", "ok")
    return redirect(url_for("attendance.staff_attendance"))


@attendance.route("/staff/attendance/check-out", methods=["POST"])
@require_login
@require_shelter
def staff_attendance_check_out_global():
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]

    rid_raw = (request.form.get("resident_id") or "").strip()
    note = (request.form.get("note") or "").strip()
    checkout_type = (request.form.get("checkout_type") or "out").strip().lower()
    expected_back_raw = (request.form.get("expected_back_at") or "").strip()

    if checkout_type not in {"out", "pass"}:
        flash("Select a valid checkout type.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    if not rid_raw.isdigit():
        flash("Select a resident.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    resident_id = int(rid_raw)

    resident = db_fetchone(
        "SELECT id FROM residents WHERE id = %s AND shelter = %s AND is_active = TRUE"
        if g.get("db_kind") == "pg"
        else "SELECT id FROM residents WHERE id = ? AND shelter = ? AND is_active = 1",
        (resident_id, shelter),
    )
    if not resident:
        flash("Invalid resident.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    if not expected_back_raw:
        flash("Expected back time is required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    try:
        local_dt = datetime.fromisoformat(expected_back_raw)
        local_dt = local_dt.replace(tzinfo=ZoneInfo("America/Chicago"))
        expected_back_value = (
            local_dt.astimezone(timezone.utc)
            .replace(tzinfo=None)
            .isoformat(timespec="seconds")
        )
    except Exception:
        flash("Invalid expected back time.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    event_time = datetime.utcnow().replace(microsecond=0).isoformat()

    stored_note = f"[{checkout_type.upper()}]"
    if note:
        stored_note = f"{stored_note} {note}"

    sql = (
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
             "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    db_execute(
        sql,
        (resident_id, shelter, "check_out", event_time, staff_id, stored_note, expected_back_value),
    )

    log_action("attendance", resident_id, shelter, staff_id, "check_out", stored_note)
    flash(
        "Resident checked out on Pass." if checkout_type == "pass" else "Resident checked out.",
        "success",
    )
    return redirect(url_for("attendance.staff_attendance"))


@attendance.route("/staff/attendance/resident/<int:resident_id>/print")
@require_login
@require_shelter
def staff_attendance_resident_print(resident_id: int):
    shelter = session["shelter"]

    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()

    resident = db_fetchone(
        "SELECT first_name, last_name FROM residents WHERE id = %s AND shelter = %s"
        if g.get("db_kind") == "pg"
        else "SELECT first_name, last_name FROM residents WHERE id = ? AND shelter = ?",
        (resident_id, shelter),
    )

    if not resident:
        abort(404)

    first = resident["first_name"] if isinstance(resident, dict) else resident[0]
    last = resident["last_name"] if isinstance(resident, dict) else resident[1]

    resident_name = f"{last}, {first}"

    params = [resident_id, shelter]
    date_filter = ""

    if start:
        date_filter += " AND ae.event_time >= %s" if g.get("db_kind") == "pg" else " AND ae.event_time >= ?"
        params.append(start + "T00:00:00")

    if end:
        date_filter += " AND ae.event_time <= %s" if g.get("db_kind") == "pg" else " AND ae.event_time <= ?"
        params.append(end + "T23:59:59")

    events_raw = db_fetchall(
        f"""
        SELECT
            ae.event_type,
            ae.event_time,
            ae.note,
            ae.expected_back_time,
            su.username
        FROM attendance_events ae
        LEFT JOIN staff_users su ON su.id = ae.staff_user_id
        WHERE ae.resident_id = {"%s" if g.get("db_kind") == "pg" else "?"}
        AND ae.shelter = {"%s" if g.get("db_kind") == "pg" else "?"}
        {date_filter}
        ORDER BY ae.event_time ASC
        """,
        tuple(params),
    )

    def local_day(dt_iso):
        try:
            dt = parse_dt(dt_iso).replace(tzinfo=timezone.utc)
            return dt.astimezone(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
        except Exception:
            return dt_iso[:10]

    events = []
    last_checkout = None

    for e in events_raw:
        event_type = e["event_type"] if isinstance(e, dict) else e[0]
        event_time = e["event_time"] if isinstance(e, dict) else e[1]
        note = e["note"] if isinstance(e, dict) else e[2]
        expected_back = e["expected_back_time"] if isinstance(e, dict) else e[3]
        staff = e["username"] if isinstance(e, dict) else e[4]

        if event_type == "check_out":
            last_checkout = {
                "checked_out_at": event_time,
                "expected_back_at": expected_back,
                "note": note,
                "out_staff": staff or "",
            }
            continue

        if event_type == "check_in" and last_checkout:
            late = None
            if last_checkout["expected_back_at"]:
                try:
                    late = parse_dt(event_time) > parse_dt(last_checkout["expected_back_at"])
                except Exception:
                    pass

            events.append({
                "date": local_day(event_time),
                "checked_out_at": last_checkout["checked_out_at"],
                "expected_back_at": last_checkout["expected_back_at"],
                "checked_in_at": event_time,
                "late": late,
                "note": last_checkout["note"],
                "out_staff": last_checkout["out_staff"],
                "in_staff": staff or "",
            })

            last_checkout = None

    return render_template(
        "staff_attendance_resident_print.html",
        resident_id=resident_id,
        resident_name=resident_name,
        shelter=shelter,
        start=start,
        end=end,
        events=events,
        fmt_dt=fmt_time_only,
        printed_on=fmt_dt(utcnow_iso()),
    )


@attendance.route("/staff/attendance/print_today")
@require_login
@require_shelter
def staff_attendance_print_today():
    shelter = session["shelter"]

    rows = db_fetchall(
        """
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            ae.event_type,
            ae.event_time,
            ae.expected_back_time,
            ae.note,
            su.username
        FROM residents r
        LEFT JOIN attendance_events ae
            ON ae.resident_id = r.id
        LEFT JOIN staff_users su
            ON su.id = ae.staff_user_id
        WHERE r.shelter = %s
        ORDER BY r.last_name, ae.event_time DESC
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            ae.event_type,
            ae.event_time,
            ae.expected_back_time,
            ae.note,
            su.username
        FROM residents r
        LEFT JOIN attendance_events ae
            ON ae.resident_id = r.id
        LEFT JOIN staff_users su
            ON su.id = ae.staff_user_id
        WHERE r.shelter = ?
        ORDER BY r.last_name, ae.event_time DESC
        """,
        (shelter,),
    )

    residents: dict[int, dict[str, Any]] = {}

    for r in rows:
        rid = r["id"] if isinstance(r, dict) else r[0]
        first = r["first_name"] if isinstance(r, dict) else r[1]
        last = r["last_name"] if isinstance(r, dict) else r[2]
        event_type = r["event_type"] if isinstance(r, dict) else r[3]
        event_time = r["event_time"] if isinstance(r, dict) else r[4]
        expected = r["expected_back_time"] if isinstance(r, dict) else r[5]
        note = r["note"] if isinstance(r, dict) else r[6]
        staff = r["username"] if isinstance(r, dict) else r[7]

        if rid not in residents:
            residents[rid] = {
                "name": f"{last}, {first}",
                "status": "IN",
                "out_time": None,
                "expected": None,
                "staff": "",
                "note": "",
            }

        if event_type == "check_out":
            residents[rid]["status"] = "OUT"
            residents[rid]["out_time"] = event_time
            residents[rid]["expected"] = expected
            residents[rid]["staff"] = staff or ""
            residents[rid]["note"] = note or ""

    return render_template(
        "staff_attendance_today_print.html",
        residents=residents.values(),
        shelter=shelter,
        printed_on=fmt_dt(utcnow_iso()),
        fmt_dt=fmt_time_only,
    )
