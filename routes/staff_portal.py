from __future__ import annotations

from flask import Blueprint, flash, redirect, session, url_for

from core.auth import can_manage_requests, require_login, require_shelter

staff_portal = Blueprint("staff_portal", __name__)


def _can_manage_leave() -> bool:
    return can_manage_requests()


def _deny_if_needed():
    if not _can_manage_leave():
        flash("Staff only.", "error")
        return redirect(url_for("auth.staff_home"))
    return None


@staff_portal.route("/staff/leave/pending")
@require_login
@require_shelter
def staff_leave_pending():
    denied = _deny_if_needed()
    if denied is not None:
        return denied

    return redirect(url_for("attendance.staff_passes_pending"))


@staff_portal.route("/staff/leave/upcoming")
@require_login
@require_shelter
def staff_leave_upcoming():
    denied = _deny_if_needed()
    if denied is not None:
        return denied

    return redirect(url_for("attendance.staff_passes_approved"))


@staff_portal.route("/staff/leave/away-now")
@require_login
@require_shelter
def staff_leave_away_now():
    denied = _deny_if_needed()
    if denied is not None:
        return denied

    return redirect(url_for("attendance.staff_attendance"))


@staff_portal.route("/staff/leave/overdue")
@require_login
@require_shelter
def staff_leave_overdue():
    denied = _deny_if_needed()
    if denied is not None:
        return denied

    return redirect(url_for("attendance.staff_attendance"))


@staff_portal.route("/staff/leave/<int:req_id>/approve", methods=["POST"])
@require_login
@require_shelter
def staff_leave_approve(req_id: int):
    denied = _deny_if_needed()
    if denied is not None:
        return denied

    flash("Legacy leave approval is retired. Use Pending Pass Requests.", "error")
    return redirect(url_for("attendance.staff_passes_pending"))


@staff_portal.route("/staff/leave/<int:req_id>/deny", methods=["POST"])
@require_login
@require_shelter
def staff_leave_deny(req_id: int):
    denied = _deny_if_needed()
    if denied is not None:
        return denied

    flash("Legacy leave denial is retired. Use Pending Pass Requests.", "error")
    return redirect(url_for("attendance.staff_passes_pending"))


@staff_portal.route("/staff/leave/<int:req_id>/check-in", methods=["POST"])
@require_login
@require_shelter
def staff_leave_check_in(req_id: int):
    denied = _deny_if_needed()
    if denied is not None:
        return denied

    flash("Legacy leave check in is retired. Use Attendance or the pass workflow.", "error")
    return redirect(url_for("attendance.staff_attendance"))


@staff_portal.get("/staff/leave/<int:req_id>/print")
@require_login
@require_shelter
def staff_leave_print(req_id: int):
    denied = _deny_if_needed()
    if denied is not None:
        return denied

    flash("Legacy leave print is retired. Open the migrated record in the pass workflow.", "error")
    return redirect(url_for("attendance.staff_passes_pending"))
