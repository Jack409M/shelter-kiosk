from flask import Blueprint, current_app, render_template, session

from core.auth import require_login, require_shelter
from core.db import db_fetchall
from core.helpers import fmt_date, fmt_dt, utcnow_iso


staff_portal = Blueprint("staff_portal", __name__)


# Simple test route to confirm blueprint wiring
@staff_portal.route("/_staff_test/attendance")
def staff_attendance_test():
    return "staff attendance blueprint working"


# Pending leave requests
@staff_portal.route("/staff/leave/pending")
@require_login
@require_shelter
def staff_leave_pending():
    shelter = session["shelter"]

    sql = (
        "SELECT * FROM leave_requests WHERE status = %s AND shelter = %s ORDER BY submitted_at DESC"
        if current_app.config.get("DATABASE_URL")
        else "SELECT * FROM leave_requests WHERE status = ? AND shelter = ? ORDER BY submitted_at DESC"
    )

    rows = db_fetchall(sql, ("pending", shelter))

    return render_template(
        "staff_leave_pending.html",
        rows=rows,
        fmt_dt=fmt_dt,
        fmt_date=fmt_date,
        shelter=shelter,
    )


# Upcoming approved leave
@staff_portal.route("/staff/leave/upcoming")
@require_login
@require_shelter
def staff_leave_upcoming():
    shelter = session["shelter"]
    now = utcnow_iso()

    sql = (
        """
        SELECT * FROM leave_requests
        WHERE status = %s AND shelter = %s AND check_in_at IS NULL AND leave_at > %s
        ORDER BY leave_at ASC
        """
        if current_app.config.get("DATABASE_URL")
        else
        """
        SELECT * FROM leave_requests
        WHERE status = ? AND shelter = ? AND check_in_at IS NULL AND leave_at > ?
        ORDER BY leave_at ASC
        """
    )

    rows = db_fetchall(sql, ("approved", shelter, now))

    return render_template(
        "staff_leave_upcoming.html",
        rows=rows,
        fmt_dt=fmt_dt,
        fmt_date=fmt_date,
        shelter=shelter,
    )

@staff_portal.route("/staff/leave/away-now")
@require_login
@require_shelter
def staff_leave_away_now():
    shelter = session["shelter"]
    now = utcnow_iso()
    rows = db_fetchall(
        """
        SELECT * FROM leave_requests
        WHERE status = %s AND shelter = %s AND leave_at <= %s AND check_in_at IS NULL
        ORDER BY return_at ASC
        """
        if current_app.config.get("DATABASE_URL")
        else """
        SELECT * FROM leave_requests
        WHERE status = ? AND shelter = ? AND leave_at <= ? AND check_in_at IS NULL
        ORDER BY return_at ASC
        """,
        ("approved", shelter, now),
    )
    return render_template("staff_leave_away_now.html", rows=rows, fmt_dt=fmt_dt, shelter=shelter)

