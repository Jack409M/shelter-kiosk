from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchone, get_db
from core.helpers import utcnow_iso
from core.rate_limit import is_rate_limited
from routes.resident_parts.consent import (
    resident_consent_view,
    sms_consent_public_alias_slash_view,
    sms_consent_public_alias_view,
    sms_consent_view,
)
from routes.resident_parts.helpers import parse_dt as _parse_dt
from routes.resident_parts.leave import resident_leave_view

resident_requests = Blueprint("resident_requests", __name__)


# Future extraction note
# This file is still a mixed workflow route file.
# The next clean split should continue like this:
#
# routes/resident_parts/signin.py
# routes/resident_parts/transport.py
#
# Already extracted:
# routes/resident_parts/helpers.py
# routes/resident_parts/consent.py
# routes/resident_parts/leave.py
#
# Additional app level imports like init_db, require_resident, and
# get_all_shelters should eventually stop coming from app.py and move
# into dedicated core modules or resident service helpers.


def _client_ip() -> str:
    """
    Use Flask's normalized remote address.
    Falls back to a stable placeholder if missing.
    """
    return (request.remote_addr or "").strip() or "unknown"


@resident_requests.route("/resident", methods=["GET", "POST"])
def resident_signin():
    # Future extraction note
    # Move signin and logout together into resident_parts/signin.py.
    from app import init_db
    from core.residents import resident_session_start

    init_db()

    next_url = (request.args.get("next") or request.form.get("next") or "").strip()

    if request.method == "GET":
        return render_template("resident_signin.html")

    ip = _client_ip()
    if is_rate_limited(f"resident_signin:{ip}", limit=30, window_seconds=300):
        flash("Too many sign in attempts. Please wait a few minutes and try again.", "error")
        return render_template("resident_signin.html"), 429

    resident_code = (request.form.get("resident_code") or "").strip()

    row = db_fetchone(
        "SELECT * FROM residents WHERE resident_code = %s"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM residents WHERE resident_code = ?",
        (resident_code,),
    )

    if not row:
        flash("Invalid Resident Code.", "error")
        return render_template("resident_signin.html"), 401

    shelter = ((row.get("shelter") if isinstance(row, dict) else row[1]) or "").strip()
    resident_session_start(row, shelter, resident_code)

    allowed_next = {
        url_for("resident_requests.resident_leave"),
        url_for("resident_requests.resident_transport"),
        url_for("resident_portal.home"),
    }

    if next_url not in allowed_next:
        next_url = url_for("resident_portal.home")

    if not session.get("sms_consent_done"):
        return redirect(url_for("resident_requests.resident_consent", next=next_url))

    return redirect(next_url)


@resident_requests.get("/resident/logout")
def resident_logout():
    for k in [
        "resident_id",
        "resident_identifier",
        "resident_first",
        "resident_last",
        "resident_phone",
        "resident_shelter",
        "resident_code",
        "sms_consent_done",
        "sms_opt_in",
    ]:
        session.pop(k, None)

    return redirect(url_for("resident_requests.resident_signin"))


@resident_requests.route("/leave", methods=["GET", "POST"])
def resident_leave():
    return resident_leave_view()


@resident_requests.route("/transport", methods=["GET", "POST"])
def resident_transport():
    # Future extraction note
    # Move this full transport workflow into resident_parts/transport.py.
    from app import init_db, require_resident

    @require_resident
    def _inner():
        init_db()

        shelter = session.get("resident_shelter") or ""

        if request.method == "GET":
            return render_template("resident_transport.html", shelter=shelter)

        resident_identifier = session.get("resident_identifier") or ""
        first = session.get("resident_first") or ""
        last = session.get("resident_last") or ""

        ip = _client_ip()
        rl_key = f"resident_transport:{ip}:{resident_identifier or 'unknown'}"
        if is_rate_limited(rl_key, limit=6, window_seconds=900):
            flash("Too many transportation submissions. Please wait a few minutes and try again.", "error")
            return render_template("resident_transport.html", shelter=shelter), 429

        needed_raw = (request.form.get("needed_at") or "").strip()
        pickup = (request.form.get("pickup_location") or "").strip()
        destination = (request.form.get("destination") or "").strip()
        reason = (request.form.get("reason") or "").strip()
        resident_notes = (request.form.get("resident_notes") or "").strip()
        callback_phone = (request.form.get("callback_phone") or "").strip()

        errors: list[str] = []
        if not first or not last or not needed_raw or not pickup or not destination:
            errors.append("Complete all required fields.")

        try:
            needed_local = _parse_dt(needed_raw)
            needed_dt = (
                needed_local.replace(tzinfo=ZoneInfo("America/Chicago"))
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )
            if needed_dt < datetime.utcnow() - timedelta(minutes=1):
                errors.append("Needed time cannot be in the past.")
        except Exception:
            errors.append("Invalid needed date or time.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("resident_transport.html", shelter=shelter), 400

        sql = (
            """
            INSERT INTO transport_requests
            (shelter, resident_identifier, first_name, last_name, needed_at, pickup_location, destination, reason, resident_notes, callback_phone, status, submitted_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
            RETURNING id
            """
            if g.get("db_kind") == "pg"
            else """
            INSERT INTO transport_requests
            (shelter, resident_identifier, first_name, last_name, needed_at, pickup_location, destination, reason, resident_notes, callback_phone, status, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """
        )

        needed_iso = needed_dt.replace(microsecond=0).isoformat()
        submitted = utcnow_iso()

        params = (
            shelter,
            resident_identifier,
            first,
            last,
            needed_iso,
            pickup,
            destination,
            reason or None,
            resident_notes or None,
            callback_phone or None,
            submitted,
        )

        if g.get("db_kind") == "pg":
            conn = get_db()
            cur = conn.cursor()
            cur.execute(sql, params)
            req_id = cur.fetchone()[0]
            cur.close()
        else:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            req_id = cur.lastrowid
            cur.close()

        log_action("transport", req_id, shelter, None, "create", "Resident submitted transport request")
        flash("Your transportation request was submitted successfully.", "ok")
        return redirect(url_for("resident_portal.home"))

    return _inner()


@resident_requests.get("/sms-consent")
def sms_consent_public_alias():
    return sms_consent_public_alias_view()


@resident_requests.get("/sms-consent/")
def sms_consent_public_alias_slash():
    return sms_consent_public_alias_slash_view()


@resident_requests.get("/resident/sms-consent")
def sms_consent():
    return sms_consent_view()


@resident_requests.route("/resident/consent", methods=["GET", "POST"])
def resident_consent():
    return resident_consent_view()
