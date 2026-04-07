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


def _checkout_category_map_for_shelter(shelter: str) -> dict[str, dict]:
    return {
        (row.get("activity_label") or "").strip(): row
        for row in _active_checkout_categories_for_shelter(shelter)
        if (row.get("activity_label") or "").strip()
    }


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


def _parse_stored_utc_naive(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _late_status(expected_back_time: str | None, is_out: bool) -> tuple[bool, int | None]:
    if not is_out:
        return False, None

    expected_back_dt = _parse_stored_utc_naive(expected_back_time)
    if not expected_back_dt:
        return False, None

    now_utc = datetime.now(timezone.utc)
    if now_utc <= expected_back_dt:
        return False, None

    late_seconds = (now_utc - expected_back_dt).total_seconds()
    late_minutes = max(1, int(late_seconds // 60))
    return True, late_minutes


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


def _latest_completed_attendance_pair(resident_id: int, shelter: str):
    checkin_row = db_fetchone(
        """
        SELECT id, event_time
        FROM attendance_events
        WHERE resident_id = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(%s))
          AND event_type = %s
        ORDER BY event_time DESC, id DESC
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT id, event_time
        FROM attendance_events
        WHERE resident_id = ?
          AND LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(?))
          AND event_type = ?
        ORDER BY event_time DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter, "check_in"),
    )

    if not checkin_row:
        return None

    checkin_id = int(checkin_row["id"] if isinstance(checkin_row, dict) else checkin_row[0])
    checkin_time = (checkin_row["event_time"] if isinstance(checkin_row, dict) else checkin_row[1]) or ""

    checkout_row = db_fetchone(
        """
        SELECT
            id,
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
          AND event_type = %s
          AND event_time <= %s
        ORDER BY event_time DESC, id DESC
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT
            id,
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
          AND event_type = ?
          AND event_time <= ?
        ORDER BY event_time DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter, "check_out", checkin_time),
    )

    if not checkout_row:
        return None

    return {
        "checkin_id": checkin_id,
        "checkin_time": checkin_time,
        "checkout_id": int(checkout_row["id"] if isinstance(checkout_row, dict) else checkout_row[0]),
        "checkout_time": (checkout_row["event_time"] if isinstance(checkout_row, dict) else checkout_row[1]) or "",
        "note": (checkout_row["note"] if isinstance(checkout_row, dict) else checkout_row[2]) or "",
        "expected_back_time": (checkout_row["expected_back_time"] if isinstance(checkout_row, dict) else checkout_row[3]) or "",
        "destination": (checkout_row["destination"] if isinstance(checkout_row, dict) else checkout_row[4]) or "",
        "obligation_start_time": (checkout_row["obligation_start_time"] if isinstance(checkout_row, dict) else checkout_row[5]) or "",
        "obligation_end_time": (checkout_row["obligation_end_time"] if isinstance(checkout_row, dict) else checkout_row[6]) or "",
        "actual_obligation_end_time": (checkout_row["actual_obligation_end_time"] if isinstance(checkout_row, dict) else checkout_row[7]) or "",
    }


def _checkout_requires_actual_end_time_from_values(
    destination: str | None,
    obligation_start_time: str | None,
    obligation_end_time: str | None,
) -> bool:
    return bool(
        (destination or "").strip()
        and (obligation_start_time or "").strip()
        and (obligation_end_time or "").strip()
    )


def _checkout_requires_actual_end_time(checkout_row) -> bool:
    if not checkout_row:
        return False

    destination = (checkout_row["destination"] if isinstance(checkout_row, dict) else checkout_row[5]) or ""
    obligation_start = (checkout_row["obligation_start_time"] if isinstance(checkout_row, dict) else checkout_row[6]) or ""
    obligation_end = (checkout_row["obligation_end_time"] if isinstance(checkout_row, dict) else checkout_row[7]) or ""

    return _checkout_requires_actual_end_time_from_values(destination, obligation_start, obligation_end)


def _attendance_insert_sql() -> str:
    return (
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time, destination, obligation_start_time, obligation_end_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time, destination, obligation_start_time, obligation_end_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )


def _attendance_base_row(r, shelter: str) -> dict[str, Any]:
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
    last_completed_pair = None if is_out else _latest_completed_attendance_pair(rid, shelter)
    is_late, late_minutes = _late_status(expected_back_time, is_out)

    return {
        "resident_id": rid,
        "first_name": first,
        "last_name": last,
        "name": f"{last}, {first}",
        "checked_out_at": checkout_time,
        "expected_back_at": expected_back_time,
        "is_out": is_out,
        "is_late": is_late,
        "late_minutes": late_minutes,
        "note": checkout_note,
        "destination": destination,
        "obligation_start_at": obligation_start_time,
        "obligation_end_at": obligation_end_time,
        "actual_obligation_end_at": actual_obligation_end_time,
        "checkout_time_input": _local_dt_input_value(checkout_time),
        "obligation_start_input": _local_dt_input_value(obligation_start_time),
        "obligation_end_input": _local_dt_input_value(obligation_end_time),
        "actual_obligation_end_input": _local_dt_input_value(actual_obligation_end_time),
        "has_active_pass": active_pass,
        "actual_end_required": bool(destination and obligation_start_time and obligation_end_time),
        "last_completed_pair": last_completed_pair,
        "last_completed_checkout_time_input": _local_dt_input_value(last_completed_pair["checkout_time"]) if last_completed_pair else "",
        "last_completed_checkin_time_input": _local_dt_input_value(last_completed_pair["checkin_time"]) if last_completed_pair else "",
        "last_completed_destination": last_completed_pair["destination"] if last_completed_pair else "",
        "last_completed_start_input": _local_dt_input_value(last_completed_pair["obligation_start_time"]) if last_completed_pair else "",
        "last_completed_end_input": _local_dt_input_value(last_completed_pair["obligation_end_time"]) if last_completed_pair else "",
        "last_completed_actual_end_input": _local_dt_input_value(last_completed_pair["actual_obligation_end_time"]) if last_completed_pair else "",
        "last_completed_actual_end_required": _checkout_requires_actual_end_time_from_values(
            last_completed_pair["destination"] if last_completed_pair else "",
            last_completed_pair["obligation_start_time"] if last_completed_pair else "",
            last_completed_pair["obligation_end_time"] if last_completed_pair else "",
        ),
    }


def staff_attendance_view():
    shelter = session["shelter"]
    checkout_categories = _active_checkout_categories_for_shelter(shelter)

    residents = db_fetchall(
        "SELECT * FROM residents WHERE shelter = %s AND is_active = TRUE ORDER BY last_name, first_name"
        if current_app.config.get("DATABASE_URL")
        else "SELECT * FROM residents WHERE shelter = ? AND is_active = 1 ORDER BY last_name, first_name",
        (shelter,),
    )

    out_rows: list[dict[str, Any]] = []
    in_rows: list[dict[str, Any]] = []

    for r in residents:
        row = _attendance_base_row(r, shelter)
        if row["is_out"]:
            out_rows.append(row)
        else:
            in_rows.append(row)

    out_rows.sort(
        key=lambda x: (
            0 if x["is_late"] else 1,
            x["last_name"].lower(),
            x["first_name"].lower(),
        )
    )
    in_rows.sort(key=lambda x: (x["last_name"].lower(), x["first_name"].lower()))

    return render_template(
        "staff_attendance.html",
        out_rows=out_rows,
        in_rows=in_rows,
        fmt_time=fmt_time_only,
        shelter=shelter,
        checkout_categories=checkout_categories,
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
        requires_actual_end = _checkout_requires_actual_end_time(open_checkout)
        existing_actual_end = (open_checkout["actual_obligation_end_time"] if isinstance(open_checkout, dict) else open_checkout[8]) or ""
        if requires_actual_end and not existing_actual_end:
            flash("This resident needs an actual obligation end time before check in. Use Edit.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

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


def _resident_for_edit_or_redirect(resident_id: int, shelter: str):
    resident = db_fetchone(
        "SELECT * FROM residents WHERE id = %s AND shelter = %s AND is_active = TRUE"
        if current_app.config.get("DATABASE_URL")
        else "SELECT * FROM residents WHERE id = ? AND shelter = ? AND is_active = 1",
        (resident_id, shelter),
    )
    if not resident:
        flash("Resident not found.", "error")
        return None
    return resident


def staff_attendance_edit_open_view(resident_id: int):
    shelter = session["shelter"]
    resident = _resident_for_edit_or_redirect(resident_id, shelter)
    if not resident:
        return redirect(url_for("attendance.staff_attendance"))

    open_checkout = _latest_open_checkout_row(resident_id, shelter)
    if not open_checkout:
        flash("No open attendance record found to edit.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    row = _attendance_base_row(resident, shelter)
    return render_template(
        "staff_attendance_edit.html",
        mode="open",
        shelter=shelter,
        resident=row,
        checkout_categories=_active_checkout_categories_for_shelter(shelter),
    )


def staff_attendance_edit_open_submit_view(resident_id: int):
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]

    resident = _resident_for_edit_or_redirect(resident_id, shelter)
    if not resident:
        return redirect(url_for("attendance.staff_attendance"))

    open_checkout = _latest_open_checkout_row(resident_id, shelter)
    if not open_checkout:
        flash("No open attendance record found to edit.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    checkout_time_raw = (request.form.get("checkout_at") or "").strip()
    destination_raw = (request.form.get("destination") or "").strip()
    start_raw = (request.form.get("obligation_start_at") or "").strip()
    end_raw = (request.form.get("obligation_end_at") or "").strip()
    actual_end_raw = (request.form.get("actual_obligation_end_at") or "").strip()

    if not checkout_time_raw:
        flash("Checkout time is required.", "error")
        return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

    try:
        updated_checkout_time = _parse_datetime_local_to_utc_naive(checkout_time_raw)
    except Exception:
        flash("Invalid checkout time.", "error")
        return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

    if not destination_raw:
        flash("Activity category is required.", "error")
        return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

    category_map = _checkout_category_map_for_shelter(shelter)
    selected_category = category_map.get(destination_raw)
    if not selected_category:
        flash("Select a valid activity category.", "error")
        return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

    requires_approved_pass = bool(selected_category.get("requires_approved_pass"))
    existing_expected_back = (open_checkout["expected_back_time"] if isinstance(open_checkout, dict) else open_checkout[4]) or ""

    updated_expected_back = existing_expected_back
    updated_start = None
    updated_end = None
    updated_actual_end = None

    if requires_approved_pass:
        active_pass = _active_pass_row(resident_id, shelter)
        if not active_pass:
            flash("No approved pass found for that activity category.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

        updated_expected_back = _pass_expected_back_value(active_pass)
        if not updated_expected_back:
            flash("Approved pass is missing an end time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))
    else:
        if not start_raw:
            flash("Scheduled start time is required.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

        if not end_raw:
            flash("Scheduled end time is required.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

        if not actual_end_raw:
            flash("Actual obligation end time is required.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

        try:
            updated_start = _parse_datetime_local_to_utc_naive(start_raw)
        except Exception:
            flash("Invalid scheduled start time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

        try:
            updated_end = _parse_datetime_local_to_utc_naive(end_raw)
        except Exception:
            flash("Invalid scheduled end time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

        try:
            updated_actual_end = _parse_datetime_local_to_utc_naive(actual_end_raw)
        except Exception:
            flash("Invalid actual obligation end time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

        if updated_end < updated_start:
            flash("Scheduled end time cannot be earlier than scheduled start time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

        if updated_actual_end < updated_start:
            flash("Actual end time cannot be earlier than scheduled start time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

        if updated_actual_end > utcnow_iso():
            flash("Actual end time cannot be later than right now.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_open", resident_id=resident_id))

    checkout_id = int(open_checkout["id"] if isinstance(open_checkout, dict) else open_checkout[0])

    db_execute(
        """
        UPDATE attendance_events
        SET event_time = %s,
            destination = %s,
            expected_back_time = %s,
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
        SET event_time = ?,
            destination = ?,
            expected_back_time = ?,
            obligation_start_time = ?,
            obligation_end_time = ?,
            actual_obligation_end_time = ?
        WHERE id = ?
          AND resident_id = ?
          AND shelter = ?
        """,
        (
            updated_checkout_time,
            destination_raw,
            updated_expected_back,
            updated_start,
            updated_end,
            updated_actual_end,
            checkout_id,
            resident_id,
            shelter,
        ),
    )

    log_action(
        "attendance",
        resident_id,
        shelter,
        staff_id,
        "edit_open_attendance",
        (
            f"checkout={updated_checkout_time} "
            f"destination={destination_raw} "
            f"expected_back={updated_expected_back or ''} "
            f"start={updated_start or ''} "
            f"end={updated_end or ''} "
            f"actual_end={updated_actual_end or ''}"
        ).strip(),
    )
    flash("Open attendance record updated.", "ok")
    return redirect(url_for("attendance.staff_attendance"))


def staff_attendance_edit_last_view(resident_id: int):
    shelter = session["shelter"]
    resident = _resident_for_edit_or_redirect(resident_id, shelter)
    if not resident:
        return redirect(url_for("attendance.staff_attendance"))

    row = _attendance_base_row(resident, shelter)
    if not row["last_completed_pair"]:
        flash("No completed attendance record found to edit.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    return render_template(
        "staff_attendance_edit.html",
        mode="last",
        shelter=shelter,
        resident=row,
        checkout_categories=_active_checkout_categories_for_shelter(shelter),
    )


def staff_attendance_edit_last_submit_view(resident_id: int):
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]

    resident = _resident_for_edit_or_redirect(resident_id, shelter)
    if not resident:
        return redirect(url_for("attendance.staff_attendance"))

    pair = _latest_completed_attendance_pair(resident_id, shelter)
    if not pair:
        flash("No completed attendance record found to edit.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    checkout_time_raw = (request.form.get("checkout_at") or "").strip()
    checkin_time_raw = (request.form.get("checkin_at") or "").strip()
    destination_raw = (request.form.get("destination") or "").strip()
    start_raw = (request.form.get("obligation_start_at") or "").strip()
    end_raw = (request.form.get("obligation_end_at") or "").strip()
    actual_end_raw = (request.form.get("actual_obligation_end_at") or "").strip()

    if not checkout_time_raw:
        flash("Checkout time is required.", "error")
        return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

    if not checkin_time_raw:
        flash("Check in time is required.", "error")
        return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

    try:
        updated_checkout_time = _parse_datetime_local_to_utc_naive(checkout_time_raw)
    except Exception:
        flash("Invalid checkout time.", "error")
        return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

    try:
        updated_checkin_time = _parse_datetime_local_to_utc_naive(checkin_time_raw)
    except Exception:
        flash("Invalid check in time.", "error")
        return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

    if updated_checkin_time < updated_checkout_time:
        flash("Check in time cannot be earlier than checkout time.", "error")
        return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

    if not destination_raw:
        flash("Activity category is required.", "error")
        return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

    category_map = _checkout_category_map_for_shelter(shelter)
    selected_category = category_map.get(destination_raw)
    if not selected_category:
        flash("Select a valid activity category.", "error")
        return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

    requires_approved_pass = bool(selected_category.get("requires_approved_pass"))
    updated_expected_back = pair["expected_back_time"] or ""
    updated_start = None
    updated_end = None
    updated_actual_end = None

    if requires_approved_pass:
        if destination_raw != (pair["destination"] or ""):
            flash("Completed attendance cannot be changed into a different pass based category after the fact.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))
    else:
        if not start_raw:
            flash("Scheduled start time is required.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

        if not end_raw:
            flash("Scheduled end time is required.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

        if not actual_end_raw:
            flash("Actual obligation end time is required.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

        try:
            updated_start = _parse_datetime_local_to_utc_naive(start_raw)
        except Exception:
            flash("Invalid scheduled start time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

        try:
            updated_end = _parse_datetime_local_to_utc_naive(end_raw)
        except Exception:
            flash("Invalid scheduled end time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

        try:
            updated_actual_end = _parse_datetime_local_to_utc_naive(actual_end_raw)
        except Exception:
            flash("Invalid actual obligation end time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

        if updated_end < updated_start:
            flash("Scheduled end time cannot be earlier than scheduled start time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

        if updated_actual_end < updated_start:
            flash("Actual end time cannot be earlier than scheduled start time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

        if updated_actual_end > updated_checkin_time:
            flash("Actual end time cannot be later than the check in time.", "error")
            return redirect(url_for("attendance.staff_attendance_edit_last", resident_id=resident_id))

    db_execute(
        """
        UPDATE attendance_events
        SET event_time = %s,
            destination = %s,
            expected_back_time = %s,
            obligation_start_time = %s,
            obligation_end_time = %s,
            actual_obligation_end_time = %s
        WHERE id = %s
          AND resident_id = %s
          AND shelter = %s
        """
        if g.get("db_kind") == "pg"
        else """
        UPDATE attendance_events
        SET event_time = ?,
            destination = ?,
            expected_back_time = ?,
            obligation_start_time = ?,
            obligation_end_time = ?,
            actual_obligation_end_time = ?
        WHERE id = ?
          AND resident_id = ?
          AND shelter = ?
        """,
        (
            updated_checkout_time,
            destination_raw,
            updated_expected_back,
            updated_start,
            updated_end,
            updated_actual_end,
            pair["checkout_id"],
            resident_id,
            shelter,
        ),
    )

    db_execute(
        """
        UPDATE attendance_events
        SET event_time = %s
        WHERE id = %s
          AND resident_id = %s
          AND shelter = %s
        """
        if g.get("db_kind") == "pg"
        else """
        UPDATE attendance_events
        SET event_time = ?
        WHERE id = ?
          AND resident_id = ?
          AND shelter = ?
        """,
        (
            updated_checkin_time,
            pair["checkin_id"],
            resident_id,
            shelter,
        ),
    )

    log_action(
        "attendance",
        resident_id,
        shelter,
        staff_id,
        "edit_last_attendance",
        (
            f"checkout={updated_checkout_time} "
            f"checkin={updated_checkin_time} "
            f"destination={destination_raw} "
            f"expected_back={updated_expected_back or ''} "
            f"start={updated_start or ''} "
            f"end={updated_end or ''} "
            f"actual_end={updated_actual_end or ''}"
        ).strip(),
    )
    flash("Last attendance record updated.", "ok")
    return redirect(url_for("attendance.staff_attendance"))
