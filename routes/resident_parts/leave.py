from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import flash, g, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.audit import log_action
from core.db import get_db
from core.helpers import utcnow_iso
from core.rate_limit import is_rate_limited
from core.runtime import init_db


# Resident leave workflow
#
# Future extraction note
# If this area grows, split into:
# leave_validation.py
# leave_queries.py


def _client_ip() -> str:
    return (request.remote_addr or "").strip() or "unknown"


def resident_leave_view():

    @require_resident
    def _inner():
        init_db()

        shelter = session.get("resident_shelter") or ""

        if request.method == "GET":
            return render_template("resident_leave.html", shelter=shelter)

        resident_identifier = (session.get("resident_identifier") or "").strip()
        first = (session.get("resident_first") or "").strip()
        last = (session.get("resident_last") or "").strip()
        resident_phone = (session.get("resident_phone") or "").strip()

        ip = _client_ip()
        rl_key = f"resident_leave:{ip}:{resident_identifier or 'unknown'}"
        if is_rate_limited(rl_key, limit=6, window_seconds=900):
            flash("Too many leave submissions. Please wait a few minutes and try again.", "error")
            return render_template("resident_leave.html", shelter=shelter), 429

        leave_date_raw = (request.form.get("leave_date") or "").strip()
        return_date_raw = (request.form.get("return_date") or "").strip()
        destination = (request.form.get("destination") or "").strip()
        reason = (request.form.get("reason") or "").strip()
        resident_notes = (request.form.get("resident_notes") or "").strip()

        errors: list[str] = []

        if not first or not last or not leave_date_raw or not return_date_raw or not destination:
            errors.append("Complete all required fields.")

        leave_dt = None
        return_dt = None

        try:
            leave_local_date = datetime.strptime(leave_date_raw, "%Y-%m-%d").date()
            return_local_date = datetime.strptime(return_date_raw, "%Y-%m-%d").date()

            leave_local_dt = datetime.combine(
                leave_local_date,
                datetime.strptime("08:00", "%H:%M").time(),
            ).replace(tzinfo=ZoneInfo("America/Chicago"))

            return_local_dt = datetime.combine(
                return_local_date,
                datetime.strptime("22:00", "%H:%M").time(),
            ).replace(tzinfo=ZoneInfo("America/Chicago"))

            leave_dt = leave_local_dt.astimezone(timezone.utc).replace(tzinfo=None)
            return_dt = return_local_dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            errors.append("Invalid date.")

        if leave_dt and return_dt:
            if return_dt < leave_dt:
                errors.append("Return date cannot be earlier than leave date.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("resident_leave.html", shelter=shelter), 400

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
