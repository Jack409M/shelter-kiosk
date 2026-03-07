from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import fmt_date, fmt_dt, fmt_pretty_date, utcnow_iso
from core.audit import log_action


staff_portal = Blueprint("staff_portal", __name__)


@staff_portal.route("/_staff_test/attendance")
def staff_attendance_test():
    return "staff attendance blueprint working"


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

    sql = (
        """
        SELECT * FROM leave_requests
        WHERE status = %s AND shelter = %s AND leave_at <= %s AND check_in_at IS NULL
        ORDER BY return_at ASC
        """
        if current_app.config.get("DATABASE_URL")
        else
        """
        SELECT * FROM leave_requests
        WHERE status = ? AND shelter = ? AND leave_at <= ? AND check_in_at IS NULL
        ORDER BY return_at ASC
        """
    )

    rows = db_fetchall(sql, ("approved", shelter, now))

    return render_template(
        "staff_leave_away_now.html",
        rows=rows,
        fmt_dt=fmt_dt,
        shelter=shelter,
    )


@staff_portal.route("/staff/leave/overdue")
@require_login
@require_shelter
def staff_leave_overdue():
    shelter = session["shelter"]

    sql = (
        """
        SELECT * FROM leave_requests
        WHERE status = %s AND shelter = %s AND check_in_at IS NULL
        ORDER BY return_at ASC
        """
        if current_app.config.get("DATABASE_URL")
        else
        """
        SELECT * FROM leave_requests
        WHERE status = ? AND shelter = ? AND check_in_at IS NULL
        ORDER BY return_at ASC
        """
    )

    rows = db_fetchall(sql, ("approved", shelter))

    now_local = datetime.now(ZoneInfo("America/Chicago"))
    overdue_rows = []

    for r in rows:
        return_iso = r["return_at"] if isinstance(r, dict) or hasattr(r, "__getitem__") else None
        if not return_iso:
            continue

        try:
            rt_utc = datetime.fromisoformat(return_iso).replace(tzinfo=timezone.utc)
            rt_local = rt_utc.astimezone(ZoneInfo("America/Chicago"))
            cutoff_local = rt_local.replace(hour=22, minute=0, second=0, microsecond=0)

            if now_local > cutoff_local:
                overdue_rows.append(r)
        except Exception:
            continue

    return render_template(
        "staff_leave_overdue.html",
        rows=overdue_rows,
        fmt_dt=fmt_dt,
        fmt_date=fmt_date,
        shelter=shelter,
    )


@staff_portal.route("/staff/leave/<int:req_id>/approve", methods=["POST"])
@require_login
@require_shelter
def staff_leave_approve(req_id: int):
    from app import send_sms

    shelter = session["shelter"]
    staff_id = session["staff_user_id"]
    note = (request.form.get("note") or "").strip()

    row = db_fetchone(
        "SELECT * FROM leave_requests WHERE id = %s AND shelter = %s"
        if current_app.config.get("DATABASE_URL")
        else "SELECT * FROM leave_requests WHERE id = ? AND shelter = ?",
        (req_id, shelter),
    )

    if not row or (row["status"] if isinstance(row, dict) else row[10]) != "pending":
        flash("Not pending.", "error")
        return redirect(url_for("staff_portal.staff_leave_pending"))

    decided_at = utcnow_iso()

    sql = (
        """
        UPDATE leave_requests
        SET status = %s, decided_at = %s, decided_by = %s, decision_note = %s
        WHERE id = %s AND shelter = %s
        """
        if current_app.config.get("DATABASE_URL")
        else
        """
        UPDATE leave_requests
        SET status = ?, decided_at = ?, decided_by = ?, decision_note = ?
        WHERE id = ? AND shelter = ?
        """
    )

    db_execute(
        sql,
        ("approved", decided_at, staff_id, note or None, req_id, shelter),
    )

    log_action("leave", req_id, shelter, staff_id, "approve", note or "")

    req = db_fetchone(
        "SELECT first_name, last_name, leave_at, return_at, resident_phone FROM leave_requests WHERE id = %s AND shelter = %s"
        if current_app.config.get("DATABASE_URL")
        else "SELECT first_name, last_name, leave_at, return_at, resident_phone FROM leave_requests WHERE id = ? AND shelter = ?",
        (req_id, shelter),
    )

    if req:
        first_name = req["first_name"] if isinstance(req, dict) else req[0]
        last_name = req["last_name"] if isinstance(req, dict) else req[1]
        leave_at = req["leave_at"] if isinstance(req, dict) else req[2]
        return_at = req["return_at"] if isinstance(req, dict) else req[3]
        phone = req["resident_phone"] if isinstance(req, dict) else req[4]

        msg = (
            f"Leave approved for {first_name} {last_name}. "
            f"Leave {fmt_pretty_date(leave_at)}. "
            f"Return {fmt_pretty_date(return_at)} by 10 PM."
        )

        try:
            if phone:
                send_sms(phone, msg)
        except Exception as e:
            log_action("leave", req_id, shelter, staff_id, "sms_failed", str(e))

    flash("Approved.", "ok")
    return redirect(url_for("staff_portal.staff_leave_pending"))


@staff_portal.route("/staff/leave/<int:req_id>/deny", methods=["POST"])
@require_login
@require_shelter
def staff_leave_deny(req_id: int):
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]
    note = (request.form.get("note") or "").strip()

    if not note:
        flash("Denial note required.", "error")
        return redirect(url_for("staff_portal.staff_leave_pending"))

    sql = (
        """
        UPDATE leave_requests
        SET status = %s, decided_at = %s, decided_by = %s, decision_note = %s
        WHERE id = %s AND shelter = %s AND status = %s
        """
        if current_app.config.get("DATABASE_URL")
        else
        """
        UPDATE leave_requests
        SET status = ?, decided_at = ?, decided_by = ?, decision_note = ?
        WHERE id = ? AND shelter = ? AND status = ?
        """
    )

    db_execute(
        sql,
        ("denied", utcnow_iso(), staff_id, note, req_id, shelter, "pending"),
    )

    log_action("leave", req_id, shelter, staff_id, "deny", note)
    flash("Denied.", "ok")
    return redirect(url_for("staff_portal.staff_leave_pending"))

@staff_portal.route("/staff/leave/<int:req_id>/check-in", methods=["POST"])
@require_login
@require_shelter
def staff_leave_check_in(req_id: int):
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]
    note = (request.form.get("note") or "").strip()

    sql = (
        """
        UPDATE leave_requests
        SET status = %s, check_in_at = %s, check_in_by = %s
        WHERE id = %s AND shelter = %s AND status = %s AND check_in_at IS NULL
        """
        if current_app.config.get("DATABASE_URL")
        else
        """
        UPDATE leave_requests
        SET status = ?, check_in_at = ?, check_in_by = ?
        WHERE id = ? AND shelter = ? AND status = ? AND check_in_at IS NULL
        """
    )

    db_execute(
        sql,
        ("checked_in", utcnow_iso(), staff_id, req_id, shelter, "approved"),
    )

    log_action("leave", req_id, shelter, staff_id, "check_in", note or "")
    flash("Checked in.", "ok")
    return redirect(url_for("staff_portal.staff_leave_away_now"))

@staff_portal.get("/staff/leave/<int:req_id>/print")
@require_login
@require_shelter
@require_staff_or_admin
def staff_leave_print(req_id: int):
    init_db()

    shelter = session["shelter"]
    

    row = db_fetchone(
        """
        SELECT
            lr.*,
            r.first_name,
            r.last_name,
            COALESCE(su.username, '') AS decided_by_name,
            COALESCE(su.role, '') AS decided_by_role
        FROM leave_requests lr
        LEFT JOIN residents r
            ON r.resident_identifier = lr.resident_identifier
            AND r.shelter = lr.shelter
        LEFT JOIN staff_users su
            ON su.id = lr.decided_by
        WHERE lr.id = %s AND lr.shelter = %s
        """
        if current_app.config.get("DATABASE_URL")
        else
        """
        SELECT
            lr.*,
            r.first_name,
            r.last_name,
            COALESCE(su.username, '') AS decided_by_name,
            COALESCE(su.role, '') AS decided_by_role
        FROM leave_requests lr
        LEFT JOIN residents r
            ON r.resident_identifier = lr.resident_identifier
            AND r.shelter = lr.shelter
        LEFT JOIN staff_users su
            ON su.id = lr.decided_by
        WHERE lr.id = ? AND lr.shelter = ?
        """,
        (req_id, shelter),
    )

    if not row:
        abort(404)

    return render_template(
        "staff_leave_print.html",
        row=row,
        shelter=shelter,
        printed_on=fmt_dt(utcnow_iso()),
        fmt_dt=fmt_dt,
        fmt_date=fmt_date,
    )
