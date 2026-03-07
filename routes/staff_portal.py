from flask import Blueprint, render_template
from core.auth import require_login, require_shelter
from core.helpers import utcnow_iso, fmt_date, fmt_dt

staff_portal = Blueprint("staff_portal", __name__)


@staff_portal.route("/_staff_test/attendance")
def staff_attendance_test():
    return "staff attendance blueprint working"

from flask import session, g

@staff_portal.route("/_staff_test/leave/pending")
@require_login
@require_shelter
def staff_leave_pending_test():
    shelter = session["shelter"]

    rows = db_fetchall(
        "SELECT * FROM leave_requests WHERE status = %s AND shelter = %s ORDER BY submitted_at DESC"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM leave_requests WHERE status = ? AND shelter = ? ORDER BY submitted_at DESC",
        ("pending", shelter),
    )

    return render_template(
        "staff_leave_pending.html",
        rows=rows,
        fmt_dt=fmt_dt,
        fmt_date=fmt_date,
        shelter=shelter,
    )
