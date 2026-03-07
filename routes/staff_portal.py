from flask import Blueprint, current_app, render_template, session

from core.auth import require_login, require_shelter
from core.db import db_fetchall
from core.helpers import fmt_date, fmt_dt


staff_portal = Blueprint("staff_portal", __name__)


@staff_portal.route("/_staff_test/attendance")
def staff_attendance_test():
    return "staff attendance blueprint working"


@staff_portal.route("/staff/leave/pending")
@require_login
@require_shelter
def staff_leave_pending_test():
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
