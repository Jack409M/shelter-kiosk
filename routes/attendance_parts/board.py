from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from flask import current_app, flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import fmt_time_only, utcnow_iso
from core.residents import has_active_pass
from routes.attendance_parts.helpers import complete_active_passes


def staff_attendance_view():
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
            ORDER BY event_time DESC, id DESC
            LIMIT 1
            """
            if current_app.config.get("DATABASE_URL")
            else """
            SELECT event_type, event_time, expected_back_time, note
            FROM attendance_events
            WHERE resident_id = ? AND shelter = ?
            ORDER BY event_time DESC, id DESC
            LIMIT 1
            """,
            (rid, shelter),
        )

        last_event_type = ""
        if last_event:
            last_event_type = last_event["event_type"] if isinstance(last_event, dict) else last_event[0]

        last_checkout = db_fetchone(
            """
            SELECT event_time, expected_back_time, note, destination, obligation_start_time, obligation_end_time
            FROM attendance_events
            WHERE resident_id = %s AND shelter = %s AND event_type = %s
            ORDER BY event_time DESC, id DESC
            LIMIT 1
            """
            if current_app.config.get("DATABASE_URL")
            else """
            SELECT event_time, expected_back_time, note, destination, obligation_start_time, obligation_end_time
            FROM attendance_events
            WHERE resident_id = ? AND shelter = ? AND event_type = ?
            ORDER BY event_time DESC, id DESC
            LIMIT 1
            """,
            (rid, shelter, "check_out"),
        )

        checkout_time = ""
        expected_back_time = ""
        checkout_note = ""
        destination = ""
        obligation_start_time = ""
        obligation_end_time = ""

        if last_checkout:
            checkout_time = last_checkout["event_time"] if isinstance(last_checkout, dict) else last_checkout[0]
            expected_back_time = last_checkout["expected_back_time"] if isinstance(last_checkout, dict) else (last_checkout[1] or "")
            checkout_note = (last_checkout["note"] if isinstance(last_checkout, dict) else last_checkout[2]) or ""
            destination = (last_checkout["destination"] if isinstance(last_checkout, dict) else last_checkout[3]) or ""
            obligation_start_time = (last_checkout["obligation_start_time"] if isinstance(last_checkout, dict) else last_checkout[4]) or ""
            obligation_end_time = (last_checkout["obligation_end_time"] if isinstance(last_checkout, dict) else last_checkout[5]) or ""

        is_out = last_event_type == "check_out"
        active_pass = has_active_pass(rid, shelter)

        row = {
            "resident_id": rid,
            "first_name": first,
            "last_name": last,
            "name": f"{last}, {first}",
            "checked_out_at": checkout_time,
            "expected_back_at": expected_back_time,
            "is_out": is_out,
            "note": checkout_note,
            "destination": destination,
            "obligation_start_at": obligation_start_time,
            "obligation_end_at": obligation_end_time,
            "has_active_pass": active_pass,
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


def staff_attendance_check_in_view(resident_id: int):
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
        INSERT INTO attendance_events (
            resident_id,
            shelter,
            event_type,
            event_time,
            staff_user_id,
            note,
            expected_back_time,
            destination,
            obligation_start_time,
            obligation_end_time
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        if current_app.config.get("DATABASE_URL")
        else """
        INSERT INTO attendance_events (
            resident_id,
            shelter,
            event_type,
            event_time,
            staff_user_id,
            note,
            expected_back_time,
            destination,
            obligation_start_time,
            obligation_end_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (resident_id, shelter, "check_in", utcnow_iso(), staff_id, "Manual check in", None, None, None, None),
    )

    complete_active_passes(resident_id, shelter)

    log_action("attendance", resident_id, shelter, staff_id, "check_in", "Manual check in")
    flash("Resident checked in.", "ok")
    return redirect(url_for("attendance.staff_attendance"))


def staff_attendance_check_out_global_view():
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
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time, destination, obligation_start_time, obligation_end_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time, destination, obligation_start_time, obligation_end_time) "
             "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )

    db_execute(
        sql,
        (resident_id, shelter, "check_out", event_time, staff_id, stored_note, expected_back_value, None, None, None),
    )

    log_action("attendance", resident_id, shelter, staff_id, "check_out", stored_note)
    flash(
        "Resident checked out on Pass." if checkout_type == "pass" else "Resident checked out.",
        "success",
    )
    return redirect(url_for("attendance.staff_attendance"))
