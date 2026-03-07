from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso

attendance = Blueprint("attendance", __name__)


# -----------------------------------------------------
# Staff Attendance Board
# -----------------------------------------------------

@attendance.route("/staff/attendance")
@require_login
@require_shelter
def staff_attendance():
    shelter = session.get("shelter")

    rows = db_fetchall(
        """
        SELECT *
        FROM attendance
        WHERE shelter = %s
        ORDER BY checked_out_at DESC
        """
        if shelter else
        """
        SELECT *
        FROM attendance
        ORDER BY checked_out_at DESC
        """,
        (shelter,) if shelter else ()
    )

    return render_template(
        "staff_attendance.html",
        rows=rows,
    )


# -----------------------------------------------------
# Check In Resident
# FIXED ROUTE: removed double slash and restored param
# -----------------------------------------------------

@attendance.route("/staff/attendance/<int:resident_id>/check-in", methods=["POST"])
@require_login
@require_shelter
def staff_attendance_check_in(resident_id):

    db_execute(
        """
        UPDATE attendance
        SET checked_in_at = %s,
            checked_out_at = NULL
        WHERE resident_id = %s
        """,
        (utcnow_iso(), resident_id)
    )

    flash("Resident checked in.", "success")

    return redirect(url_for("attendance.staff_attendance"))


# -----------------------------------------------------
# Check Out Resident
# -----------------------------------------------------

@attendance.route("/staff/attendance/check-out", methods=["POST"])
@require_login
@require_shelter
def staff_attendance_check_out():

    resident_id = request.form.get("resident_id")

    if not resident_id:
        flash("Missing resident.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    db_execute(
        """
        UPDATE attendance
        SET checked_out_at = %s
        WHERE resident_id = %s
        """,
        (utcnow_iso(), resident_id)
    )

    flash("Resident checked out.", "success")

    return redirect(url_for("attendance.staff_attendance"))


# -----------------------------------------------------
# Print Today
# -----------------------------------------------------

@attendance.route("/staff/attendance/print_today")
@require_login
@require_shelter
def staff_attendance_print_today():

    rows = db_fetchall(
        """
        SELECT *
        FROM attendance
        ORDER BY checked_out_at DESC
        """
    )

    return render_template(
        "staff_attendance_print.html",
        rows=rows,
    )


# -----------------------------------------------------
# Print Resident History
# FIXED ROUTE: restored resident_id parameter
# -----------------------------------------------------

@attendance.route("/staff/attendance/resident/<int:resident_id>/print")
@require_login
@require_shelter
def staff_attendance_resident_print(resident_id):

    rows = db_fetchall(
        """
        SELECT *
        FROM attendance
        WHERE resident_id = %s
        ORDER BY checked_out_at DESC
        """,
        (resident_id,)
    )

    return render_template(
        "staff_attendance_resident_print.html",
        rows=rows,
    )
