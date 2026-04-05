from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from flask import current_app, flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import fmt_time_only, utcnow_iso
from core.kiosk_activity_categories import load_kiosk_activity_categories_for_shelter
from core.residents import has_active_pass
from routes.attendance_parts.helpers import complete_active_passes


def _active_checkout_categories_for_shelter(shelter: str) -> list[dict]:
    shelter_key = (shelter or "").strip().lower()
    rows = load_kiosk_activity_categories_for_shelter(shelter_key)

    categories: list[dict] = []
    for row in rows or []:
        label = (row.get("activity_label") or "").strip()
        if not label:
            continue
        if not row.get("active"):
            continue
        categories.append(dict(row))

    return categories


def _editable_checkout_categories_for_shelter(shelter: str) -> list[dict]:
    rows = _active_checkout_categories_for_shelter(shelter)
    return [row for row in rows if not bool(row.get("requires_approved_pass"))]


def _active_pass_row(resident_id: int, shelter: str):
    normalized_shelter = (shelter or "").strip().lower()
    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    return db_fetchone(
        """
        SELECT id, pass_type, destination, end_at, end_date
        FROM resident_passes
        WHERE resident_id = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = %s
          AND status = %s
          AND (
                (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at <= %s AND end_at >= %s)
             OR (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= %s AND end_date >= %s)
          )
        ORDER BY
            CASE WHEN end_at IS NULL THEN 1 ELSE 0 END,
            end_at ASC,
            end_date ASC,
            id ASC
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT id, pass_type, destination, end_at, end_date
        FROM resident_passes
        WHERE resident_id = ?
          AND LOWER(TRIM(COALESCE(shelter, ''))) = ?
          AND status = ?
          AND (
                (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at <= ? AND end_at >= ?)
             OR (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= ? AND end_date >= ?)
          )
        ORDER BY
            CASE WHEN end_at IS NULL THEN 1 ELSE 0 END,
            end_at ASC,
            end_date ASC,
            id ASC
        LIMIT 1
        """,
        (resident_id, normalized_shelter, "approved", now_iso, now_iso, today_iso, today_iso),
    )


def _pass_expected_back_value(pass_row) -> str | None:
    if not pass_row:
        return None

    end_at = (pass_row["end_at"] if isinstance(pass_row, dict) else pass_row[3]) or ""
    end_at = str(end_at).strip()
    if end_at:
        return end_at

    end_date = (pass_row["end_date"] if isinstance(pass_row, dict) else pass_row[4]) or ""
    end_date = str(end_date).strip()
    if not end_date:
        return None

    local_end = datetime.combine(
        datetime.fromisoformat(end_date).date(),
        datetime.min.time().replace(hour=23, minute=59, second=59),
        tzinfo=ZoneInfo("America/Chicago"),
    )

    return (
        local_end.astimezone(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def _parse_datetime_local_to_utc_naive(value: str) -> str:
    local_dt = datetime.fromisoformat((value or "").strip())
    local_dt = local_dt.replace(tzinfo=ZoneInfo("America/Chicago"))
    return (
        local_dt.astimezone(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def _local_dt_input_value(dt_iso: str | None) -> str:
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(str(dt_iso)).replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo("America/Chicago"))
        return local_dt.strftime("%Y-%m-%dT%H:%M")
    except Exception:
        return ""


def _latest_open_checkout_row(resident_id: int, shelter: str):
    row = db_fetchone(
        """
        SELECT
            id,
            event_type,
            event_time,
            note,
            expected_back_time,
            destination,
            obligation_start_time,
            obligation_end_time,
            actual_obligation_end_time
        FROM attendance_events
        WHERE resident_id = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(%s))
        ORDER BY event_time DESC, id DESC
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT
            id,
            event_type,
            event_time,
            note,
            expected_back_time,
            destination,
            obligation_start_time,
            obligation_end_time,
            actual_obligation_end_time
        FROM attendance_events
        WHERE resident_id = ?
          AND LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(?))
        ORDER BY event_time DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter),
    )

    if not row:
        return None

    event_type = row["event_type"] if isinstance(row, dict) else row[1]
    if (event_type or "").strip() != "check_out":
        return None

    return row


def _checkout_requires_actual_end_time(checkout_row) -> bool:
    if not checkout_row:
        return False

    destination = (checkout_row["destination"] if isinstance(checkout_row, dict) else checkout_row[5]) or ""
    obligation_start = (checkout_row["obligation_start_time"] if isinstance(checkout_row, dict) else checkout_row[6]) or ""
    obligation_end = (checkout_row["obligation_end_time"] if isinstance(checkout_row, dict) else checkout_row[7]) or ""

    return bool(str(destination).strip() and str(obligation_start).strip() and str(obligation_end).strip())


def _attendance_insert_sql() -> str:
    return (
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time, destination, obligation_start_time, obligation_end_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time, destination, obligation_start_time, obligation_end_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )


def staff_attendance_view():
    shelter = session["shelter"]
    checkout_categories = _active_checkout_categories_for_shelter(shelter)
    editable_checkout_categories = _editable_checkout_categories_for_shelter(shelter)

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
            SELECT event_time, expected_back_time, note, destination, obligation_start_time, obligation_end_time, actual_obligation_end_time
            FROM attendance_events
            WHERE resident_id = %s AND shelter = %s AND event_type = %s
            ORDER BY event_time DESC, id DESC
            LIMIT 1
            """
            if current_app.config.get("DATABASE_URL")
            else """
            SELECT event_time, expected_back_time, note, destination, obligation_start_time, obligation_end_time, actual_obligation_end_time
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
        actual_obligation_end_time = ""

        if last_checkout:
            checkout_time = last_checkout["event_time"] if isinstance(last_checkout, dict) else last_checkout[0]
            expected_back_time = last_checkout["expected_back_time"] if isinstance(last_checkout, dict) else (last_checkout[1] or "")
            checkout_note = (last_checkout["note"] if isinstance(last_checkout, dict) else last_checkout[2]) or ""
            destination = (last_checkout["destination"] if isinstance(last_checkout, dict) else last_checkout[3]) or ""
            obligation_start_time = (last_checkout["obligation_start_time"] if isinstance(last_checkout, dict) else last_checkout[4]) or ""
            obligation_end_time = (last_checkout["obligation_end_time"] if isinstance(last_checkout, dict) else last_checkout[5]) or ""
            actual_obligation_end_time = (last_checkout["actual_obligation_end_time"] if isinstance(last_checkout, dict) else last_checkout[6]) or ""

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
            "actual_obligation_end_at": actual_obligation_end_time,
            "obligation_start_input": _local_dt_input_value(obligation_start_time),
            "obligation_end_input": _local_dt_input_value(obligation_end_time),
            "actual_obligation_end_input": _local_dt_input_value(actual_obligation_end_time),
            "has_active_pass": active_pass,
            "actual_end_required": bool(destination and obligation_start_time and obligation_end_time),
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
        checkout_categories=checkout_categories,
        editable_checkout_categories=editable_checkout_categories,
        local_dt_input=_local_dt_input_value,
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

    open_checkout = _latest_open_checkout_row(resident_id, shelter)
    checkin_time_value = utcnow_iso()

    if open_checkout:
        destination_value = (request.form.get("destination") or "").strip()
        start_raw = (request.form.get("obligation_start_at") or "").strip()
        end_raw = (request.form.get("obligation_end_at") or "").strip()
        actual_end_raw = (request.form.get("actual_obligation_end_at") or "").strip()

        existing_destination = (open_checkout["destination"] if isinstance(open_checkout, dict) else open_checkout[5]) or ""
        existing_start = (open_checkout["obligation_start_time"] if isinstance(open_checkout, dict) else open_checkout[6]) or ""
        existing_end = (open_checkout["obligation_end_time"] if isinstance(open_checkout, dict) else open_checkout[7]) or ""
        existing_actual_end = (open_checkout["actual_obligation_end_time"] if isinstance(open_checkout, dict) else open_checkout[8]) or ""

        updated_destination = destination_value or existing_destination
        updated_start = existing_start
        updated_end = existing_end
        updated_actual_end = existing_actual_end

        if start_raw:
            try:
                updated_start = _parse_datetime_local_to_utc_naive(start_raw)
            except Exception:
                flash("Invalid scheduled start time.", "error")
                return redirect(url_for("attendance.staff_attendance"))

        if end_raw:
            try:
                updated_end = _parse_datetime_local_to_utc_naive(end_raw)
            except Exception:
                flash("Invalid scheduled end time.", "error")
                return redirect(url_for("attendance.staff_attendance"))

        if updated_start and updated_end and updated_end < updated_start:
            flash("Scheduled end time cannot be earlier than scheduled start time.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        requires_actual_end = bool(updated_destination and updated_start and updated_end)

        if actual_end_raw:
            try:
                updated_actual_end = _parse_datetime_local_to_utc_naive(actual_end_raw)
            except Exception:
                flash("Invalid actual obligation end time.", "error")
                return redirect(url_for("attendance.staff_attendance"))

        if requires_actual_end and not updated_actual_end:
            flash("Actual obligation end time is required before check in.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        if updated_actual_end and updated_start and updated_actual_end < updated_start:
            flash("Actual end time cannot be earlier than scheduled start time.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        if updated_actual_end and updated_actual_end > checkin_time_value:
            flash("Actual end time cannot be later than the time of check in.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        checkout_id = int(open_checkout["id"] if isinstance(open_checkout, dict) else open_checkout[0])

        db_execute(
            """
            UPDATE attendance_events
            SET destination = %s,
                obligation_start_time = %s,
                obligation_end_time = %s,
                actual_obligation_end_time = %s
            WHERE id = %s
              AND resident_id = %s
              AND shelter = %s
            """
            if current_app.config.get("DATABASE_URL")
            else """
            UPDATE attendance_events
            SET destination = ?,
                obligation_start_time = ?,
                obligation_end_time = ?,
                actual_obligation_end_time = ?
            WHERE id = ?
              AND resident_id = ?
              AND shelter = ?
            """,
            (
                updated_destination or None,
                updated_start or None,
                updated_end or None,
                updated_actual_end or None,
                checkout_id,
                resident_id,
                shelter,
            ),
        )

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
        (resident_id, shelter, "check_in", checkin_time_value, staff_id, "Manual check in", None, None, None, None),
    )

    complete_active_passes(resident_id, shelter)

    log_action("attendance", resident_id, shelter, staff_id, "check_in", "Manual check in")
    flash("Resident checked in.", "ok")
    return redirect(url_for("attendance.staff_attendance"))


def staff_attendance_check_out_global_view():
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]

    rid_raw = (request.form.get("resident_id") or "").strip()
    destination = (request.form.get("destination") or "").strip()
    note = (request.form.get("note") or "").strip()
    expected_back_raw = (request.form.get("expected_back_at") or "").strip()
    obligation_start_raw = (request.form.get("obligation_start_at") or "").strip()
    obligation_end_raw = (request.form.get("obligation_end_at") or "").strip()

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

    checkout_categories = _active_checkout_categories_for_shelter(shelter)
    category_map = {
        (item.get("activity_label") or "").strip(): item
        for item in checkout_categories
        if (item.get("activity_label") or "").strip()
    }
    selected_category = category_map.get(destination)

    if not destination:
        flash("Activity category is required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    if not selected_category:
        flash("Select a valid activity category.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    requires_approved_pass = bool(selected_category.get("requires_approved_pass"))
    expected_back_value = None
    obligation_start_value = None
    obligation_end_value = None
    note_parts: list[str] = [f"Activity Category: {destination}"]

    if requires_approved_pass:
        active_pass = _active_pass_row(resident_id, shelter)
        if not active_pass:
            flash("No approved pass found for that activity category.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        expected_back_value = _pass_expected_back_value(active_pass)
        if not expected_back_value:
            flash("Approved pass is missing an end time.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        pass_id = active_pass["id"] if isinstance(active_pass, dict) else active_pass[0]
        pass_type = (active_pass["pass_type"] if isinstance(active_pass, dict) else active_pass[1]) or ""
        pass_destination = (active_pass["destination"] if isinstance(active_pass, dict) else active_pass[2]) or ""

        if pass_id:
            note_parts.append(f"Pass ID: {pass_id}")
        if pass_type:
            note_parts.append(f"Pass Type: {pass_type}")
        if pass_destination:
            note_parts.append(f"Pass Destination: {pass_destination}")
    else:
        if not obligation_start_raw:
            flash("Scheduled start time is required.", "error")
            return redirect(url_for("attendance.staff_attendance"))
        if not obligation_end_raw:
            flash("Scheduled end time is required.", "error")
            return redirect(url_for("attendance.staff_attendance"))
        if not expected_back_raw:
            flash("Expected back time is required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        try:
            obligation_start_value = _parse_datetime_local_to_utc_naive(obligation_start_raw)
        except Exception:
            flash("Invalid scheduled start time.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        try:
            obligation_end_value = _parse_datetime_local_to_utc_naive(obligation_end_raw)
        except Exception:
            flash("Invalid scheduled end time.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        try:
            expected_back_value = _parse_datetime_local_to_utc_naive(expected_back_raw)
        except Exception:
            flash("Invalid expected back time.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        if obligation_end_value < obligation_start_value:
            flash("Scheduled end time cannot be earlier than scheduled start time.", "error")
            return redirect(url_for("attendance.staff_attendance"))

    if note:
        note_parts.append(note)

    full_note = " | ".join(note_parts) if note_parts else None
    event_time = utcnow_iso()

    db_execute(
        _attendance_insert_sql(),
        (
            resident_id,
            shelter,
            "check_out",
            event_time,
            staff_id,
            full_note,
            expected_back_value,
            destination,
            obligation_start_value,
            obligation_end_value,
        ),
    )

    log_action(
        "attendance",
        resident_id,
        shelter,
        staff_id,
        "check_out",
        (
            f"destination={destination or ''} "
            f"start={obligation_start_value or ''} "
            f"end={obligation_end_value or ''} "
            f"expected_back={expected_back_value or ''}"
        ).strip(),
    )
    flash("Resident checked out.", "success")
    return redirect(url_for("attendance.staff_attendance"))
