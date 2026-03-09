from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchone, get_db
from core.helpers import utcnow_iso
from core.rate_limit import is_rate_limited


resident_requests = Blueprint("resident_requests", __name__)


def _parse_dt(dt_str: str) -> datetime:
    """
    Parse an ISO formatted datetime string from form input.
    """
    return datetime.fromisoformat(dt_str)


def _client_ip() -> str:
    """
    Use Flask's normalized remote address.
    Falls back to a stable placeholder if missing.
    """
    return (request.remote_addr or "").strip() or "unknown"


@resident_requests.route("/resident", methods=["GET", "POST"])
def resident_signin():
    from app import init_db
    from core.residents import resident_session_start

    init_db()

    next_url = (request.args.get("next") or request.form.get("next") or "").strip()

    if request.method == "GET":
        return render_template("resident_signin.html")

    # Public endpoint protection.
    # Use a higher threshold because many residents may share one kiosk IP.
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
    from app import MAX_LEAVE_DAYS, SHELTERS, init_db, require_resident

    @require_resident
    def _inner():
        init_db()

        shelter = session.get("resident_shelter") or ""

        if request.method == "GET":
            return render_template("resident_leave.html", shelter=shelter, max_days=MAX_LEAVE_DAYS)

        resident_identifier = session.get("resident_identifier") or ""
        first = session.get("resident_first") or ""
        last = session.get("resident_last") or ""

        # Resident specific throttle so one shared kiosk IP does not block everyone.
        ip = _client_ip()
        rl_key = f"resident_leave:{ip}:{resident_identifier or 'unknown'}"
        if is_rate_limited(rl_key, limit=6, window_seconds=900):
            flash("Too many leave submissions. Please wait a few minutes and try again.", "error")
            return render_template(
                "resident_leave.html",
                shelters=SHELTERS,
                shelter=shelter,
                max_days=MAX_LEAVE_DAYS,
            ), 429

        resident_phone = (request.form.get("resident_phone") or "").strip()
        if resident_phone:
            db_execute(
                "UPDATE residents SET phone = %s WHERE shelter = %s AND resident_identifier = %s"
                if g.get("db_kind") == "pg"
                else "UPDATE residents SET phone = ? WHERE shelter = ? AND resident_identifier = ?",
                (resident_phone, shelter, resident_identifier),
            )
            session["resident_phone"] = resident_phone

        destination = (request.form.get("destination") or "").strip()
        reason = (request.form.get("reason") or "").strip()
        resident_notes = (request.form.get("resident_notes") or "").strip()
        leave_at_raw = (request.form.get("leave_at") or "").strip()
        return_at_raw = (request.form.get("return_at") or "").strip()
        agreed = request.form.get("agreed") == "on"

        errors: list[str] = []

        if not agreed:
            errors.append("You must accept the agreement.")

        if not first or not last or not destination or not leave_at_raw or not return_at_raw:
            errors.append("Complete all required fields.")

        try:
            leave_local_date = datetime.fromisoformat(leave_at_raw).date()
            return_local_date = datetime.fromisoformat(return_at_raw).date()

            if return_local_date < leave_local_date:
                errors.append("Return must be after leave.")

            if return_local_date > leave_local_date + timedelta(days=MAX_LEAVE_DAYS):
                errors.append(f"Maximum leave is {MAX_LEAVE_DAYS} days.")

            leave_local_dt = datetime.combine(
                leave_local_date,
                datetime.min.time(),
            ).replace(tzinfo=ZoneInfo("America/Chicago"))

            return_local_dt = datetime.combine(
                return_local_date,
                datetime.strptime("22:00", "%H:%M").time(),
            ).replace(tzinfo=ZoneInfo("America/Chicago"))

            leave_dt = leave_local_dt.astimezone(timezone.utc).replace(tzinfo=None)
            return_dt = return_local_dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            errors.append("Invalid date.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "resident_leave.html",
                shelters=SHELTERS,
                shelter=shelter,
                max_days=MAX_LEAVE_DAYS,
            ), 400

        sql = (
            """
            INSERT INTO leave_requests
            (shelter, resident_identifier, first_name, last_name, resident_phone, destination, reason, resident_notes, leave_at, return_at, status, submitted_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
            RETURNING id
            """
            if g.get("db_kind") == "pg"
            else """
            INSERT INTO leave_requests
            (shelter, resident_identifier, first_name, last_name, resident_phone, destination, reason, resident_notes, leave_at, return_at, status, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """
        )

        leave_iso = leave_dt.replace(microsecond=0).isoformat()
        return_iso = return_dt.replace(microsecond=0).isoformat()
        submitted = utcnow_iso()

        params = (
            shelter,
            resident_identifier,
            first,
            last,
            resident_phone or None,
            destination,
            reason or None,
            resident_notes or None,
            leave_iso,
            return_iso,
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

        log_action("leave", req_id, shelter, None, "create", "Resident submitted leave request")
        flash("Your leave request was submitted successfully.", "ok")
        return redirect(url_for("resident_portal.home"))

    return _inner()


@resident_requests.route("/transport", methods=["GET", "POST"])
def resident_transport():
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

        # Resident specific throttle so one shared kiosk IP does not block everyone.
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
    return redirect("/resident/sms-consent", code=302)


@resident_requests.get("/sms-consent/")
def sms_consent_public_alias_slash():
    return redirect("/sms-consent", code=301)


@resident_requests.get("/resident/sms-consent")
def sms_consent():
    return """
    <html>
        <head>
            <title>SMS Consent - Downtown Women’s Center</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; line-height: 1.6;">
            <h2>SMS Updates from Downtown Women’s Center</h2>

            <p>
                To receive SMS updates regarding shelter leave approvals, transportation notifications,
                and service reminders, text <strong>JOIN</strong> to <strong>+1 806 639 4503</strong>.
            </p>

            <p>
                Message frequency varies. Message and data rates may apply.
                Reply STOP to opt out. Reply HELP for help.
            </p>

            <p>
                <a href="/privacy">Privacy Policy</a><br>
                <a href="/terms">Terms and Conditions</a>
            </p>
        </body>
    </html>
    """


@resident_requests.route("/resident/consent", methods=["GET", "POST"])
def resident_consent():
    from app import SHELTERS, init_db

    init_db()

    next_url = (request.args.get("next") or request.form.get("next") or "").strip()

    allowed_next = {
        url_for("resident_requests.resident_leave"),
        url_for("resident_requests.resident_transport"),
        url_for("resident_portal.home"),
    }

    if next_url not in allowed_next:
        next_url = url_for("resident_portal.home")

    resident_id = session.get("resident_id")
    resident_identifier = session.get("resident_identifier") or ""
    shelter = session.get("resident_shelter") or ""

    if not resident_id or shelter not in SHELTERS:
        flash("Please sign in again.", "error")
        return redirect(url_for("resident_requests.resident_signin", next=next_url))

    if request.method == "GET":
        return render_template("resident_consent.html", next=next_url)

    # Resident specific throttle on consent posts.
    ip = _client_ip()
    rl_key = f"resident_consent:{ip}:{resident_identifier or resident_id}"
    if is_rate_limited(rl_key, limit=10, window_seconds=300):
        flash("Too many consent attempts. Please wait a few minutes and try again.", "error")
        return render_template("resident_consent.html", next=next_url), 429

    choice = (request.form.get("choice") or "").strip().lower()
    if choice not in ["accept", "decline"]:
        flash("Select accept or decline.", "error")
        return render_template("resident_consent.html", next=next_url), 400

    now = utcnow_iso()
    kind = g.get("db_kind")

    if choice == "accept":
        session["sms_consent_done"] = True
        session["sms_opt_in"] = True

        db_execute(
            """
            UPDATE residents
            SET sms_opt_in = %s,
                sms_opt_in_at = %s,
                sms_opt_in_source = %s,
                sms_opt_out_at = NULL,
                sms_opt_out_source = NULL
            WHERE id = %s AND shelter = %s
            """
            if kind == "pg"
            else """
            UPDATE residents
            SET sms_opt_in = ?,
                sms_opt_in_at = ?,
                sms_opt_in_source = ?,
                sms_opt_out_at = NULL,
                sms_opt_out_source = NULL
            WHERE id = ? AND shelter = ?
            """,
            (True if kind == "pg" else 1, now, "resident_kiosk_web_form", resident_id, shelter),
        )

    else:
        session["sms_consent_done"] = True
        session["sms_opt_in"] = False

        db_execute(
            """
            UPDATE residents
            SET sms_opt_in = %s,
                sms_opt_out_at = %s,
                sms_opt_out_source = %s
            WHERE id = %s AND shelter = %s
            """
            if kind == "pg"
            else """
            UPDATE residents
            SET sms_opt_in = ?,
                sms_opt_out_at = ?,
                sms_opt_out_source = ?
            WHERE id = ? AND shelter = ?
            """,
            (False if kind == "pg" else 0, now, "resident_kiosk_web_form_decline", resident_id, shelter),
        )

    return redirect(next_url)


@resident_requests.get("/resident/login")
def resident_login_alias():
    return redirect("/resident", code=302)


@resident_requests.get("/resident/login/")
def resident_login_alias_slash():
    return redirect("/resident", code=301)
