from __future__ import annotations

import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import KIOSK_PIN, get_all_shelters, get_client_ip, init_db

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


@kiosk.route("/kiosk/<shelter>/checkout", methods=["GET", "POST"])
def kiosk_checkout(shelter: str):
    from core.rate_limit import (
        get_key_lock_seconds_remaining,
        is_key_locked,
        is_rate_limited,
        lock_key,
    )

    init_db()

    matched_shelter = next(
        (name for name in get_all_shelters() if name.lower() == shelter.lower()),
        None,
    )
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

    if KIOSK_PIN:
        if session.get(f"kiosk_authed_{shelter}") is not True:
            if is_rate_limited(f"kiosk_pin_ip:{ip}", limit=10, window_seconds=300) or is_rate_limited(
                f"kiosk_pin_shelter:{shelter}", limit=40, window_seconds=300
            ):
                log_action(
                    "kiosk",
                    None,
                    shelter,
                    None,
                    "kiosk_pin_rate_limited",
                    f"ip={ip}",
                )
                flash("Too many PIN attempts. Please wait and try again.", "error")
                return render_template(
                    "kiosk_pin.html",
                    shelter=shelter,
                    post_url=url_for("kiosk.kiosk_checkout", shelter=shelter),
                ), 429

            if request.method == "POST":
                entered_pin = (request.form.get("kiosk_pin") or "").strip()

                if secrets.compare_digest(entered_pin, KIOSK_PIN):
                    session[f"kiosk_authed_{shelter}"] = True
                    session.permanent = True
                    return redirect(url_for("kiosk.kiosk_checkout", shelter=shelter))

                log_action(
                    "kiosk",
                    None,
                    shelter,
                    None,
                    "kiosk_pin_failed",
                    f"ip={ip}",
                )
                flash("Invalid PIN.", "error")

            return render_template(
                "kiosk_pin.html",
                shelter=shelter,
                post_url=url_for("kiosk.kiosk_checkout", shelter=shelter),
            ), 401

    if request.method == "GET":
        return render_template("kiosk_checkout.html", shelter=shelter)

    resident_code = (request.form.get("resident_code") or "").strip()
    destination = (request.form.get("destination") or "").strip()
    expected_back = (request.form.get("expected_back_time") or "").strip()
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

    if not expected_back:
        errors.append("Expected back time is required.")

    row = db_fetchone(
        "SELECT id FROM residents WHERE shelter = %s AND resident_code = %s AND is_active = TRUE"
        if g.get("db_kind") == "pg"
        else "SELECT id FROM residents WHERE shelter = ? AND resident_code = ? AND is_active = 1",
        (shelter, resident_code),
    )

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
    if expected_back:
        try:
            local_dt = datetime.fromisoformat(expected_back).replace(
                tzinfo=ZoneInfo("America/Chicago")
            )
            expected_back_value = (
                local_dt.astimezone(timezone.utc)
                .replace(tzinfo=None)
                .isoformat(timespec="seconds")
            )
        except Exception:
            errors.append("Invalid expected back time.")

    if errors:
        for e in errors:
            flash(e, "error")
        log_action(
            "kiosk",
            None,
            shelter,
            None,
            "kiosk_checkout_failed",
            f"ip={ip} resident_code={code_key} errors={' | '.join(errors)}",
        )
        return render_template("kiosk_checkout.html", shelter=shelter), 400

    resident_id = int(row["id"] if isinstance(row, dict) else row[0])

    full_note = f"Destination: {destination}"
    if note:
        full_note = f"{full_note} | Note: {note}"

    sql = (
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    db_execute(
        sql,
        (resident_id, shelter, "check_out", utcnow_iso(), None, full_note, expected_back_value),
    )

    log_action(
        "attendance",
        resident_id,
        shelter,
        None,
        "kiosk_check_out",
        f"expected_back={expected_back_value or ''} {full_note}".strip(),
    )

    flash("Checked out.", "ok")
    return redirect(url_for("kiosk.kiosk_checkout", shelter=shelter))
