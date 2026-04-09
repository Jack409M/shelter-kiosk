from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, time as time_cls, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.kiosk_activity_categories import (
    AA_NA_PARENT_ACTIVITY_LABEL,
    load_active_kiosk_activity_child_options_for_shelter,
    load_kiosk_activity_categories_for_shelter,
)
from core.runtime import get_all_shelters, get_client_ip, init_db
from routes.attendance_parts.helpers import complete_active_passes

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


def _active_aa_na_child_options_for_shelter(shelter: str) -> list[dict]:
    shelter_key = (shelter or "").strip().lower()
    rows = load_active_kiosk_activity_child_options_for_shelter(
        shelter_key,
        AA_NA_PARENT_ACTIVITY_LABEL,
    )

    options: list[dict] = []
    for row in rows or []:
        option_label = (row.get("option_label") or "").strip()
        if not option_label:
            continue
        options.append(dict(row))

    return options


def _latest_open_checkout_row(resident_id: int, shelter: str):
    row = db_fetchone(
        """
        SELECT
            id,
            event_type,
            event_time,
            destination,
            obligation_start_time,
            obligation_end_time,
            actual_obligation_end_time
        FROM attendance_events
        WHERE resident_id = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = %s
        ORDER BY event_time DESC, id DESC
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT
            id,
            event_type,
            event_time,
            destination,
            obligation_start_time,
            obligation_end_time,
            actual_obligation_end_time
        FROM attendance_events
        WHERE resident_id = ?
          AND LOWER(TRIM(COALESCE(shelter, ''))) = ?
        ORDER BY event_time DESC, id DESC
        LIMIT 1
        """,
        (resident_id, (shelter or "").strip().lower()),
    )

    if not row:
        return None

    if (_row_get(row, "event_type", 1, "") or "").strip() != "check_out":
        return None

    return row


def _checkout_requires_actual_end_time(checkout_row) -> bool:
    if not checkout_row:
        return False

    destination = (_row_get(checkout_row, "destination", 3, "") or "").strip()
    obligation_start = (_row_get(checkout_row, "obligation_start_time", 4, "") or "").strip()
    obligation_end = (_row_get(checkout_row, "obligation_end_time", 5, "") or "").strip()

    return bool(destination and obligation_start and obligation_end)


@kiosk.route("/kiosk/<shelter>")
def kiosk_home(shelter: str):
    init_db()

    matched_shelter = _resolve_shelter_or_404(shelter)
    if not matched_shelter:
        return "Invalid shelter", 404

    display_shelter = matched_shelter
    shelter_key = matched_shelter.strip().lower()
    ip = get_client_ip()

    if not _kiosk_enabled():
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_disabled_block",
            f"ip={ip}",
        )
        return "Kiosk intake is temporarily disabled.", 503

    return render_template("kiosk_home.html", shelter=display_shelter)


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

    display_shelter = matched_shelter
    shelter_key = matched_shelter.strip().lower()
    ip = get_client_ip()

    if not _kiosk_enabled():
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_disabled_block",
            f"ip={ip}",
        )
        return "Kiosk intake is temporarily disabled.", 503

    if request.method == "GET":
        return render_template(
            "kiosk_checkin.html",
            shelter=display_shelter,
            actual_end_required=False,
            prior_activity_label="",
        )

    resident_code = (request.form.get("resident_code") or "").strip()
    code_key = resident_code if resident_code else "blank"

    actual_end_hour = (request.form.get("actual_end_hour") or "").strip()
    actual_end_minute = (request.form.get("actual_end_minute") or "").strip()
    actual_end_ampm = (request.form.get("actual_end_ampm") or "").strip().upper()

    kiosk_cooldown_key = f"kiosk_cooldown:{shelter_key}:{ip}"
    resident_code_lock_key = f"kiosk_resident_code_lock:{shelter_key}:{code_key}"

    if is_key_locked(kiosk_cooldown_key):
        seconds_remaining = get_key_lock_seconds_remaining(kiosk_cooldown_key)
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_cooldown_blocked",
            f"ip={ip} seconds_remaining={seconds_remaining}",
        )
        flash("System cooling down. Please wait 30 seconds before trying again.", "error")
        return render_template(
            "kiosk_checkin.html",
            shelter=display_shelter,
            actual_end_required=False,
            prior_activity_label="",
        ), 429

    if is_key_locked(resident_code_lock_key):
        seconds_remaining = get_key_lock_seconds_remaining(resident_code_lock_key)
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_resident_code_locked",
            f"ip={ip} resident_code={code_key} seconds_remaining={seconds_remaining}",
        )
        flash("That Resident Code is temporarily locked. Please wait and try again.", "error")
        return render_template(
            "kiosk_checkin.html",
            shelter=display_shelter,
            actual_end_required=False,
            prior_activity_label="",
        ), 429

    if is_rate_limited(
        f"kiosk_checkin_cooldown_trigger:{shelter_key}:{ip}",
        limit=30,
        window_seconds=30,
    ):
        lock_key(kiosk_cooldown_key, 30)
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_cooldown_started",
            f"ip={ip} seconds=30",
        )
        flash("System cooling down. Please wait 30 seconds before trying again.", "error")
        return render_template(
            "kiosk_checkin.html",
            shelter=display_shelter,
            actual_end_required=False,
            prior_activity_label="",
        ), 429

    if is_rate_limited(f"kiosk_checkin_ip:{shelter_key}:{ip}", limit=15, window_seconds=60):
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_checkin_rate_limited",
            f"ip={ip}",
        )
        flash("Too many attempts. Please wait and try again.", "error")
        return render_template(
            "kiosk_checkin.html",
            shelter=display_shelter,
            actual_end_required=False,
            prior_activity_label="",
        ), 429

    errors = []

    if (not resident_code.isdigit()) or (len(resident_code) != 8):
        errors.append("Enter an 8 digit Resident Code.")

    row = _active_resident_row(shelter_key, resident_code)

    if not row:
        errors.append("Invalid Resident Code.")
        if is_rate_limited(
            f"kiosk_resident_code_fail:{shelter_key}:{code_key}",
            limit=5,
            window_seconds=300,
        ):
            lock_key(resident_code_lock_key, 180)
            log_action(
                "kiosk",
                None,
                shelter_key,
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
            shelter_key,
            None,
            "kiosk_checkin_failed",
            f"ip={ip} resident_code={code_key} errors={' | '.join(errors)}",
        )
        return render_template(
            "kiosk_checkin.html",
            shelter=display_shelter,
            actual_end_required=False,
            prior_activity_label="",
        ), 400

    resident_id = int(_row_get(row, "id", 0, 0))
    open_checkout = _latest_open_checkout_row(resident_id, shelter_key)
    actual_end_required = _checkout_requires_actual_end_time(open_checkout)
    prior_activity_label = (_row_get(open_checkout, "destination", 3, "") or "").strip()

    if actual_end_required and not (actual_end_hour and actual_end_minute and actual_end_ampm):
        return render_template(
            "kiosk_checkin.html",
            shelter=display_shelter,
            actual_end_required=True,
            prior_activity_label=prior_activity_label,
            resident_code_value=resident_code,
        )

    checkin_time_value = utcnow_iso()
    actual_obligation_end_value = None

    if actual_end_required:
        try:
            actual_obligation_end_value = _manual_time_value(
                actual_end_hour,
                actual_end_minute,
                actual_end_ampm,
            )
        except Exception:
            flash("Invalid actual obligation end time.", "error")
            return render_template(
                "kiosk_checkin.html",
                shelter=display_shelter,
                actual_end_required=True,
                prior_activity_label=prior_activity_label,
                resident_code_value=resident_code,
            ), 400

        planned_start = (_row_get(open_checkout, "obligation_start_time", 4, "") or "").strip()
        if planned_start and actual_obligation_end_value < planned_start:
            flash("Actual end time cannot be earlier than the scheduled start time.", "error")
            return render_template(
                "kiosk_checkin.html",
                shelter=display_shelter,
                actual_end_required=True,
                prior_activity_label=prior_activity_label,
                resident_code_value=resident_code,
            ), 400

        if actual_obligation_end_value > checkin_time_value:
            flash("Actual end time cannot be later than the time you are checking in.", "error")
            return render_template(
                "kiosk_checkin.html",
                shelter=display_shelter,
                actual_end_required=True,
                prior_activity_label=prior_activity_label,
                resident_code_value=resident_code,
            ), 400

        checkout_id = int(_row_get(open_checkout, "id", 0, 0))
        db_execute(
            """
            UPDATE attendance_events
            SET actual_obligation_end_time = %s
            WHERE id = %s
              AND resident_id = %s
              AND LOWER(TRIM(COALESCE(shelter, ''))) = %s
            """
            if g.get("db_kind") == "pg"
            else """
            UPDATE attendance_events
            SET actual_obligation_end_time = ?
            WHERE id = ?
              AND resident_id = ?
              AND LOWER(TRIM(COALESCE(shelter, ''))) = ?
            """,
            (actual_obligation_end_value, checkout_id, resident_id, shelter_key),
        )

    db_execute(
        _attendance_insert_sql(),
        (resident_id, shelter_key, "check_in", checkin_time_value, None, None, None, None, None, None),
    )

    complete_active_passes(resident_id, shelter_key)

    log_note = ""
    if actual_end_required and actual_obligation_end_value:
        log_note = f"actual_obligation_end_time={actual_obligation_end_value}"

    log_action(
        "attendance",
        resident_id,
        shelter_key,
        None,
        "kiosk_check_in",
        log_note,
    )

    flash("Checked in.", "ok")
    return redirect(url_for("kiosk.kiosk_home", shelter=shelter_key))


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

    display_shelter = matched_shelter
    shelter_key = matched_shelter.strip().lower()
    ip = get_client_ip()
    checkout_categories = _active_checkout_categories_for_shelter(shelter_key)
    aa_na_child_options = _active_aa_na_child_options_for_shelter(shelter_key)

    if not _kiosk_enabled():
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_disabled_block",
            f"ip={ip}",
        )
        return "Kiosk intake is temporarily disabled.", 503

    if request.method == "GET":
        return render_template(
            "kiosk_checkout.html",
            shelter=display_shelter,
            checkout_categories=checkout_categories,
            aa_na_parent_activity_label=AA_NA_PARENT_ACTIVITY_LABEL,
            aa_na_child_options=aa_na_child_options,
        )

    resident_code = (request.form.get("resident_code") or "").strip()
    destination = (request.form.get("destination") or "").strip()
    aa_na_meeting_1 = (request.form.get("aa_na_meeting_1") or "").strip()
    aa_na_meeting_2 = (request.form.get("aa_na_meeting_2") or "").strip()

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
    kiosk_cooldown_key = f"kiosk_cooldown:{shelter_key}:{ip}"
    resident_code_lock_key = f"kiosk_resident_code_lock:{shelter_key}:{code_key}"

    if is_key_locked(kiosk_cooldown_key):
        seconds_remaining = get_key_lock_seconds_remaining(kiosk_cooldown_key)
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_cooldown_blocked",
            f"ip={ip} seconds_remaining={seconds_remaining}",
        )
        flash("System cooling down. Please wait 30 seconds before trying again.", "error")
        return render_template(
            "kiosk_checkout.html",
            shelter=display_shelter,
            checkout_categories=checkout_categories,
            aa_na_parent_activity_label=AA_NA_PARENT_ACTIVITY_LABEL,
            aa_na_child_options=aa_na_child_options,
        ), 429

    if is_key_locked(resident_code_lock_key):
        seconds_remaining = get_key_lock_seconds_remaining(resident_code_lock_key)
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_resident_code_locked",
            f"ip={ip} resident_code={code_key} seconds_remaining={seconds_remaining}",
        )
        flash("That Resident Code is temporarily locked. Please wait and try again.", "error")
        return render_template(
            "kiosk_checkout.html",
            shelter=display_shelter,
            checkout_categories=checkout_categories,
            aa_na_parent_activity_label=AA_NA_PARENT_ACTIVITY_LABEL,
            aa_na_child_options=aa_na_child_options,
        ), 429

    if is_rate_limited(
        f"kiosk_checkout_cooldown_trigger:{shelter_key}:{ip}",
        limit=30,
        window_seconds=30,
    ):
        lock_key(kiosk_cooldown_key, 30)
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_cooldown_started",
            f"ip={ip} seconds=30",
        )
        flash("System cooling down. Please wait 30 seconds before trying again.", "error")
        return render_template(
            "kiosk_checkout.html",
            shelter=display_shelter,
            checkout_categories=checkout_categories,
            aa_na_parent_activity_label=AA_NA_PARENT_ACTIVITY_LABEL,
            aa_na_child_options=aa_na_child_options,
        ), 429

    if is_rate_limited(f"kiosk_checkout_ip:{shelter_key}:{ip}", limit=15, window_seconds=60):
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_checkout_rate_limited",
            f"ip={ip}",
        )
        flash("Too many attempts. Please wait and try again.", "error")
        return render_template(
            "kiosk_checkout.html",
            shelter=display_shelter,
            checkout_categories=checkout_categories,
            aa_na_parent_activity_label=AA_NA_PARENT_ACTIVITY_LABEL,
            aa_na_child_options=aa_na_child_options,
        ), 429

    errors = []

    if (not resident_code.isdigit()) or (len(resident_code) != 8):
        errors.append("Enter an 8 digit Resident Code.")

    if not destination:
        errors.append("Activity Category is required.")

    row = _active_resident_row(shelter_key, resident_code)

    if not row:
        errors.append("Invalid Resident Code.")
        if is_rate_limited(
            f"kiosk_resident_code_fail:{shelter_key}:{code_key}",
            limit=5,
            window_seconds=300,
        ):
            lock_key(resident_code_lock_key, 180)
            log_action(
                "kiosk",
                None,
                shelter_key,
                None,
                "kiosk_resident_code_lock_started",
                f"ip={ip} resident_code={code_key} seconds=180",
            )

    category_map = {
        (item.get("activity_label") or "").strip(): item
        for item in checkout_categories
        if (item.get("activity_label") or "").strip()
    }
    selected_category = category_map.get(destination)

    if destination and not selected_category:
        errors.append("Please select a valid Activity Category.")

    child_option_labels = {
        (item.get("option_label") or "").strip()
        for item in aa_na_child_options
        if (item.get("option_label") or "").strip()
    }

    is_aa_na_meeting = destination == AA_NA_PARENT_ACTIVITY_LABEL

    if is_aa_na_meeting:
        if not aa_na_meeting_1:
            errors.append("Meeting 1 is required for AA or NA Meeting.")
        elif aa_na_meeting_1 not in child_option_labels:
            errors.append("Please select a valid Meeting 1 option.")

        if aa_na_meeting_2 and aa_na_meeting_2 not in child_option_labels:
            errors.append("Please select a valid Meeting 2 option.")

        if aa_na_meeting_1 and aa_na_meeting_2 and aa_na_meeting_1 == aa_na_meeting_2:
            errors.append("Meeting 1 and Meeting 2 cannot be the same.")

    expected_back_value = None
    obligation_start_value = None
    obligation_end_value = None
    active_pass = None
    resident_id = int(_row_get(row, "id", 0, 0)) if row else 0
    destination_value = destination
    requires_approved_pass = bool(selected_category.get("requires_approved_pass")) if selected_category else False

    if requires_approved_pass:
        if resident_id:
            active_pass = _active_pass_row(resident_id, shelter_key)
        if not active_pass:
            errors.append("No approved pass found for that Activity Category.")
        else:
            expected_back_value = _pass_expected_back_value(active_pass)
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
            shelter_key,
            None,
            "kiosk_checkout_failed",
            f"ip={ip} resident_code={code_key} errors={' | '.join(errors)}",
        )
        return render_template(
            "kiosk_checkout.html",
            shelter=display_shelter,
            checkout_categories=checkout_categories,
            aa_na_parent_activity_label=AA_NA_PARENT_ACTIVITY_LABEL,
            aa_na_child_options=aa_na_child_options,
        ), 400

    note_parts = []

    if destination:
        note_parts.append(f"Activity Category: {destination}")

    if is_aa_na_meeting and aa_na_meeting_1:
        note_parts.append(f"Meeting 1: {aa_na_meeting_1}")

    if is_aa_na_meeting and aa_na_meeting_2:
        note_parts.append(f"Meeting 2: {aa_na_meeting_2}")

    if requires_approved_pass and active_pass:
        pass_id = _row_get(active_pass, "id", 0, "")
        pass_type = (_row_get(active_pass, "pass_type", 1, "") or "").strip()
        pass_destination = (_row_get(active_pass, "destination", 2, "") or "").strip()

        if pass_id:
            note_parts.append(f"Pass ID: {pass_id}")
        if pass_type:
            note_parts.append(f"Pass Type: {pass_type}")
        if pass_destination:
            note_parts.append(f"Pass Destination: {pass_destination}")

    if note:
        note_parts.append(note)

    full_note = " | ".join(note_parts) if note_parts else None

    db_execute(
        _attendance_insert_sql(),
        (
            resident_id,
            shelter_key,
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
        shelter_key,
        None,
        "kiosk_check_out",
        (
            f"destination={destination_value or ''} "
            f"meeting_1={aa_na_meeting_1 or ''} "
            f"meeting_2={aa_na_meeting_2 or ''} "
            f"start={obligation_start_value or ''} "
            f"end={obligation_end_value or ''} "
            f"expected_back={expected_back_value or ''}"
        ).strip(),
    )

    flash("Checked out.", "ok")
    return redirect(url_for("kiosk.kiosk_home", shelter=shelter_key))
