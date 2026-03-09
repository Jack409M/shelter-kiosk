from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso

kiosk = Blueprint("kiosk", __name__)


@kiosk.route("/kiosk/<shelter>/checkout", methods=["GET", "POST"])
def kiosk_checkout(shelter: str):
    from app import KIOSK_PIN, _client_ip, get_all_shelters, init_db
    from core.rate_limit import is_rate_limited

    init_db()

    matched_shelter = next(
        (name for name in get_all_shelters() if name.lower() == shelter.lower()),
        None,
    )
    if not matched_shelter:
        return "Invalid shelter", 404

    shelter = matched_shelter

    kiosk_manager_user = (os.environ.get("KIOSK_MANAGER_USER") or "").strip()
    kiosk_manager_pass = (os.environ.get("KIOSK_MANAGER_PASS") or "").strip()

    if kiosk_manager_user and kiosk_manager_pass:
        if session.get(f"kiosk_mgr_authed_{shelter}") is not True:
            if request.method == "POST" and request.form.get("kiosk_mgr_login") == "1":
                entered_user = (request.form.get("username") or "").strip()
                entered_pass = (request.form.get("password") or "").strip()

                if (
                    secrets.compare_digest(entered_user, kiosk_manager_user)
                    and secrets.compare_digest(entered_pass, kiosk_manager_pass)
                ):
                    session[f"kiosk_mgr_authed_{shelter}"] = True
                    session.permanent = True
                    return redirect(url_for("kiosk.kiosk_checkout", shelter=shelter))

                flash("Invalid kiosk manager login.", "error")

            return render_template("kiosk_manager_login.html", shelter=shelter), 401

    if KIOSK_PIN:
        if session.get(f"kiosk_authed_{shelter}") is not True:
            ip = _client_ip()

            if is_rate_limited(f"kiosk_pin_ip:{ip}", limit=10, window_seconds=300) or is_rate_limited(
                f"kiosk_pin_shelter:{shelter}", limit=40, window_seconds=300
            ):
                flash("Too many PIN attempts. Please wait and try again.", "error")
                return render_template("kiosk_pin.html", shelter=shelter), 429

            if request.method == "POST":
                entered_pin = (request.form.get("kiosk_pin") or "").strip()

                if secrets.compare_digest(entered_pin, KIOSK_PIN):
                    session[f"kiosk_authed_{shelter}"] = True
                    session.permanent = True
                    return redirect(url_for("kiosk.kiosk_checkout", shelter=shelter))

                flash("Invalid PIN.", "error")

            return render_template("kiosk_pin.html", shelter=shelter), 401

    if request.method == "GET":
        return render_template("kiosk_checkout.html", shelter=shelter)

    resident_code = (request.form.get("resident_code") or "").strip()
    destination = (request.form.get("destination") or "").strip()
    expected_back = (request.form.get("expected_back_time") or "").strip()
    note = (request.form.get("note") or "").strip()

    ip = _client_ip()
    code_key = resident_code if resident_code else "blank"

    if is_rate_limited(f"kiosk_checkout_ip:{ip}", limit=60, window_seconds=60) or is_rate_limited(
        f"kiosk_checkout_code:{code_key}", limit=20, window_seconds=3600
    ):
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

    expected_back_value = None
    if expected_back:
        try:
            local_dt = datetime.fromisoformat(expected_back).replace(tzinfo=ZoneInfo("America/Chicago"))
            expected_back_value = local_dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
        except Exception:
            errors.append("Invalid expected back time.")

    if errors:
        for e in errors:
            flash(e, "error")
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
