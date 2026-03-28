from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, time as time_cls, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import get_all_shelters, get_client_ip, init_db

kiosk = Blueprint("kiosk", __name__)


def _kiosk_enabled() -> bool:
    try:
        row = db_fetchone(
            "SELECT kiosk_intake_enabled FROM security_settings ORDER BY id ASC LIMIT 1"
        )
        if not row:
            return True
        return bool(row["kiosk_intake_enabled"] if isinstance(row, dict) else row[0])
    except Exception:
        return True


def _resolve_shelter_or_404(shelter: str) -> str | None:
    return next(
        (name for name in get_all_shelters() if name.lower() == shelter.lower()),
        None,
    )


def _row_get(row, key: str, index: int, default=None):
    if not row:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[index]
    except Exception:
        return default


def _active_resident_row(shelter: str, resident_code: str):
    normalized_shelter = (shelter or "").strip().lower()
    normalized_code = (resident_code or "").strip()

    return db_fetchone(
        """
        SELECT id
        FROM residents
        WHERE LOWER(TRIM(COALESCE(shelter, ''))) = %s
          AND TRIM(COALESCE(resident_code, '')) = %s
          AND is_active = TRUE
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT id
        FROM residents
        WHERE LOWER(TRIM(COALESCE(shelter, ''))) = ?
          AND TRIM(COALESCE(resident_code, '')) = ?
          AND is_active = 1
        """,
        (normalized_shelter, normalized_code),
    )


def _attendance_insert_sql() -> str:
    return (
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time, destination, obligation_start_time, obligation_end_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time, destination, obligation_start_time, obligation_end_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )


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


def _complete_active_passes(resident_id: int, shelter: str) -> None:
    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    db_execute(
        """
        UPDATE resident_passes
        SET status = %s,
            updated_at = %s
        WHERE resident_id = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = %s
          AND status = %s
          AND (
                (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at <= %s AND end_at >= %s)
             OR (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= %s AND end_date >= %s)
          )
        """
        if g.get("db_kind") == "pg"
        else """
        UPDATE resident_passes
        SET status = ?,
            updated_at = ?
        WHERE resident_id = ?
          AND LOWER(TRIM(COALESCE(shelter, ''))) = ?
          AND status = ?
          AND (
                (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at <= ? AND end_at >= ?)
             OR (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= ? AND end_date >= ?)
          )
        """,
        (
            "completed",
            now_iso,
            resident_id,
            (shelter or "").strip().lower(),
            "approved",
            now_iso,
            now_iso,
            today_iso,
            today_iso,
        ),
    )


def _manual_time_value(hour_text: str, minute_text: str, ampm_text: str) -> str:
    hour_int = int(hour_text)
    minute_int = int(minute_text)
    ampm_value = (ampm_text or "").strip().upper()

    if hour_int < 1 or hour_int > 12:
        raise ValueError("Invalid hour")

    if minute_int not in {0, 15, 30, 45}:
        raise ValueError("Invalid minute")

    if ampm_value not in {"AM", "PM"}:
        raise ValueError("Invalid AM or PM")

    if ampm_value == "PM" and hour_int != 12:
        hour_int += 12
    elif ampm_value == "AM" and hour_int == 12:
        hour_int = 0

    now_local = datetime.now(ZoneInfo("America/Chicago"))
    local_dt = now_local.replace(
        hour=hour_int,
        minute=minute_int,
        second=0,
        microsecond=0,
    )

    return (
        local_dt.astimezone(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def _pass_expected_back_value(pass_row) -> str | None:
    end_at = (_row_get(pass_row, "end_at", 3, "") or "").strip()
    if end_at:
        return end_at

    end_date = (_row_get(pass_row, "end_date", 4, "") or "").strip()
    if not end_date:
        return None

    local_end = datetime.combine(
        date_cls.fromisoformat(end_date),
        time_cls(23, 59, 59),
        tzinfo=ZoneInfo("America/Chicago"),
    )

    return (
        local_end.astimezone(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


@kiosk.route("/kiosk/<shelter>")
def kiosk_home(shelter: str):
    init_db()

    matched_shelter = _resolve_shelter_or_404(shelter)
    if not matched_shelter:
        return "Invalid shelter", 404

    shelter = matched_shelter
    ip = get_client_ip()

    if not _kiosk_enabled():
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_disabled_block",
            f"ip={ip}",
        )
        return "Kiosk intake is temporarily disabled.", 503

    return render_template("kiosk_home.html", shelter=shelter)


@kiosk.route("/kiosk/<shelter>/checkin", methods=["GET", "POST"])
def kiosk_checkin(shelter: str):
    from core.rate_limit import (
        get_key_lock_seconds_remaining,
        is_key_locked,
        is_rate_limited,
        lock_key,
    )

    init_db()

    matched_shelter = _resolve_shelter_or_404(shelter)
    if not matched_shelter:
        return "Invalid shelter", 404

    shelter = matched_shelter
    ip = get_client_ip()

    if not _kiosk_enabled():
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_disabled_block",
            f"ip={ip}",
        )
        return "Kiosk intake is temporarily disabled.", 503

    if request.method == "GET":
        return render_template("kiosk_checkin.html", shelter=shelter)

    resident_code = (request.form.get("resident_code") or "").strip()
    code_key = resident_code if resident_code else "blank"

    kiosk_cooldown_key = f"kiosk_cooldown:{shelter}:{ip}"
    resident_code_lock_key = f"kiosk_resident_code_lock:{shelter}:{code_key}"

    if is_key_locked(kiosk_cooldown_key):
        seconds_remaining = get_key_lock_seconds_remaining(kiosk_cooldown_key)
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_cooldown_blocked",
            f"ip={ip} seconds_remaining={seconds_remaining}",
        )
        flash("System cooling down. Please wait 30 seconds before trying again.", "error")
        return render_template("kiosk_checkin.html", shelter=shelter), 429

    if is_key_locked(resident_code_lock_key):
        seconds_remaining = get_key_lock_seconds_remaining(resident_code_lock_key)
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_resident_code_locked",
            f"ip={ip} resident_code={code_key} seconds_remaining={seconds_remaining}",
        )
        flash("That Resident Code is temporarily locked. Please wait and try again.", "error")
        return render_template("kiosk_checkin.html", shelter=shelter), 429

    if is_rate_limited(
        f"kiosk_checkin_cooldown_trigger:{shelter}:{ip}",
        limit=30,
        window_seconds=30,
    ):
        lock_key(kiosk_cooldown_key, 30)
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_cooldown_started",
            f"ip={ip} seconds=30",
        )
        flash("System cooling down. Please wait 30 seconds before trying again.", "error")
        return render_template("kiosk_checkin.html", shelter=shelter), 429

    if is_rate_limited(f"kiosk_checkin_ip:{shelter}:{ip}", limit=15, window_seconds=60):
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_checkin_rate_limited",
            f"ip={ip}",
        )
        flash("Too many attempts. Please wait and try again.", "error")
        return render_template("kiosk_checkin.html", shelter=shelter), 429

    errors = []

    if (not resident_code.isdigit()) or (len(resident_code) != 8):
        errors.append("Enter an 8 digit Resident Code.")

    row = _active_resident_row(shelter, resident_code)

    if not row:
        errors.append("Invalid Resident Code.")
        if is_rate_limited(
            f"kiosk_resident_code_fail:{shelter}:{code_key}",
            limit=5,
            window_seconds=300,
        ):
            lock_key(resident_code_lock_key, 180)
            log_action(
                "kiosk",
                None,
                shelter,
                None,
                "kiosk_resident_code_lock_started",
                f"ip={ip} resident_code={code_key} seconds=180",
            )

    if errors:
        for error_message in errors:
            flash(error_message, "error")
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_checkin_failed",
            f"ip={ip} resident_code={code_key} errors={' | '.join(errors)}",
        )
        return render_template("kiosk_checkin.html", shelter=shelter), 400

    resident_id = int(_row_get(row, "id", 0, 0))

    db_execute(
        _attendance_insert_sql(),
        (resident_id, shelter, "check_in", utcnow_iso(), None, None, None, None, None, None),
    )

    _complete_active_passes(resident_id, shelter)

    log_action(
        "attendance",
        resident_id,
        shelter,
        None,
        "kiosk_check_in",
        "",
    )

    flash("Checked in.", "ok")
    return redirect(url_for("kiosk.kiosk_home", shelter=shelter))


@kiosk.route("/kiosk/<shelter>/checkout", methods=["GET", "POST"])
def kiosk_checkout(shelter: str):
    from core.rate_limit import (
        get_key_lock_seconds_remaining,
        is_key_locked,
        is_rate_limited,
        lock_key,
    )

    init_db()

    matched_shelter = _resolve_shelter_or_404(shelter)
    if not matched_shelter:
        return "Invalid shelter", 404

    shelter = matched_shelter
    ip = get_client_ip()

    if not _kiosk_enabled():
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_disabled_block",
            f"ip={ip}",
        )
        return "Kiosk intake is temporarily disabled.", 503

    if request.method == "GET":
        return render_template("kiosk_checkout.html", shelter=shelter)

    resident_code = (request.form.get("resident_code") or "").strip()
    destination = (request.form.get("destination") or "").strip()

    start_time_hour = (request.form.get("start_time_hour") or "").strip()
    start_time_minute = (request.form.get("start_time_minute") or "").strip()
    start_time_ampm = (request.form.get("start_time_ampm") or "").strip().upper()

    end_time_hour = (request.form.get("end_time_hour") or "").strip()
    end_time_minute = (request.form.get("end_time_minute") or "").strip()
    end_time_ampm = (request.form.get("end_time_ampm") or "").strip().upper()

    expected_back_hour = (request.form.get("expected_back_hour") or "").strip()
    expected_back_minute = (request.form.get("expected_back_minute") or "").strip()
    expected_back_ampm = (request.form.get("expected_back_ampm") or "").strip().upper()

    note = (request.form.get("note") or "").strip()

    code_key = resident_code if resident_code else "blank"
    kiosk_cooldown_key = f"kiosk_cooldown:{shelter}:{ip}"
    resident_code_lock_key = f"kiosk_resident_code_lock:{shelter}:{code_key}"

    if is_key_locked(kiosk_cooldown_key):
        seconds_remaining = get_key_lock_seconds_remaining(kiosk_cooldown_key)
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_cooldown_blocked",
            f"ip={ip} seconds_remaining={seconds_remaining}",
        )
        flash("System cooling down. Please wait 30 seconds before trying again.", "error")
        return render_template("kiosk_checkout.html", shelter=shelter), 429

    if is_key_locked(resident_code_lock_key):
        seconds_remaining = get_key_lock_seconds_remaining(resident_code_lock_key)
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_resident_code_locked",
            f"ip={ip} resident_code={code_key} seconds_remaining={seconds_remaining}",
        )
        flash("That Resident Code is temporarily locked. Please wait and try again.", "error")
        return render_template("kiosk_checkout.html", shelter=shelter), 429

    if is_rate_limited(
        f"kiosk_checkout_cooldown_trigger:{shelter}:{ip}",
        limit=30,
        window_seconds=30,
    ):
        lock_key(kiosk_cooldown_key, 30)
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_cooldown_started",
            f"ip={ip} seconds=30",
        )
        flash("System cooling down. Please wait 30 seconds before trying again.", "error")
        return render_template("kiosk_checkout.html", shelter=shelter), 429

    if is_rate_limited(f"kiosk_checkout_ip:{shelter}:{ip}", limit=15, window_seconds=60):
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_checkout_rate_limited",
            f"ip={ip}",
        )
        flash("Too many attempts. Please wait and try again.", "error")
        return render_template("kiosk_checkout.html", shelter=shelter), 429

    errors = []

    if (not resident_code.isdigit()) or (len(resident_code) != 8):
        errors.append("Enter an 8 digit Resident Code.")

    if not destination:
        errors.append("Destination is required.")

    row = _active_resident_row(shelter, resident_code)

    if not row:
        errors.append("Invalid Resident Code.")
        if is_rate_limited(
            f"kiosk_resident_code_fail:{shelter}:{code_key}",
            limit=5,
            window_seconds=300,
        ):
            lock_key(resident_code_lock_key, 180)
            log_action(
                "kiosk",
                None,
                shelter,
                None,
                "kiosk_resident_code_lock_started",
                f"ip={ip} resident_code={code_key} seconds=180",
            )

    expected_back_value = None
    obligation_start_value = None
    obligation_end_value = None
    active_pass = None
    resident_id = int(_row_get(row, "id", 0, 0)) if row else 0
    destination_value = destination

    if destination == "Pass":
        if resident_id:
            active_pass = _active_pass_row(resident_id, shelter)
        if not active_pass:
            errors.append("No approved pass found.")
        else:
            expected_back_value = _pass_expected_back_value(active_pass)
            pass_destination = (_row_get(active_pass, "destination", 2, "") or "").strip()
            if pass_destination:
                destination_value = pass_destination
    else:
        if not start_time_hour or not start_time_minute or not start_time_ampm:
            errors.append("Start Time is required.")
        else:
            try:
                obligation_start_value = _manual_time_value(
                    start_time_hour,
                    start_time_minute,
                    start_time_ampm,
                )
            except Exception:
                errors.append("Invalid Start Time.")

        if not end_time_hour or not end_time_minute or not end_time_ampm:
            errors.append("End Time is required.")
        else:
            try:
                obligation_end_value = _manual_time_value(
                    end_time_hour,
                    end_time_minute,
                    end_time_ampm,
                )
            except Exception:
                errors.append("Invalid End Time.")

        if not expected_back_hour or not expected_back_minute or not expected_back_ampm:
            errors.append("Expected Back to Shelter is required.")
        else:
            try:
                expected_back_value = _manual_time_value(
                    expected_back_hour,
                    expected_back_minute,
                    expected_back_ampm,
                )
            except Exception:
                errors.append("Invalid Expected Back to Shelter.")

    if errors:
        for error_message in errors:
            flash(error_message, "error")
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_checkout_failed",
            f"ip={ip} resident_code={code_key} errors={' | '.join(errors)}",
        )
        return render_template("kiosk_checkout.html", shelter=shelter), 400

    note_parts = []

    if destination == "Pass" and active_pass:
        pass_id = _row_get(active_pass, "id", 0, "")
        pass_type = (_row_get(active_pass, "pass_type", 1, "") or "").strip()

        if pass_id:
            note_parts.append(f"Pass ID: {pass_id}")
        if pass_type:
            note_parts.append(f"Pass Type: {pass_type}")

    if note:
        note_parts.append(note)

    full_note = " | ".join(note_parts) if note_parts else None

    db_execute(
        _attendance_insert_sql(),
        (
            resident_id,
            shelter,
            "check_out",
            utcnow_iso(),
            None,
            full_note,
            expected_back_value,
            destination_value,
            obligation_start_value,
            obligation_end_value,
        ),
    )

    log_action(
        "attendance",
        resident_id,
        shelter,
        None,
        "kiosk_check_out",
        (
            f"destination={destination_value or ''} "
            f"start={obligation_start_value or ''} "
            f"end={obligation_end_value or ''} "
            f"expected_back={expected_back_value or ''}"
        ).strip(),
    )

    flash("Checked out.", "ok")
    return redirect(url_for("kiosk.kiosk_home", shelter=shelter))
