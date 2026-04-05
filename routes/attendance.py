from __future__ import annotations

from flask import Blueprint

from core.auth import require_login, require_shelter
from routes.attendance_parts.board import (
    staff_attendance_check_in_view,
    staff_attendance_check_out_global_view,
    staff_attendance_edit_last_view,
    staff_attendance_view,
)
from routes.attendance_parts.passes import (
    staff_pass_approve_view,
    staff_pass_deny_view,
    staff_pass_detail_view,
    staff_passes_approved_view,
    staff_passes_pending_view,
)
from routes.attendance_parts.print_views import (
    staff_attendance_print_today_view,
    staff_attendance_resident_print_view,
)


attendance = Blueprint("attendance", __name__)


@attendance.route("/staff/attendance")
@require_login
@require_shelter
def staff_attendance():
    return staff_attendance_view()


@attendance.route("/staff/attendance/<int:resident_id>/check-in", methods=["POST"])
@require_login
@require_shelter
def staff_attendance_check_in(resident_id: int):
    return staff_attendance_check_in_view(resident_id)


@attendance.route("/staff/attendance/check-out", methods=["POST"])
@require_login
@require_shelter
def staff_attendance_check_out_global():
    return staff_attendance_check_out_global_view()


@attendance.route("/staff/attendance/<int:resident_id>/edit-last", methods=["POST"])
@require_login
@require_shelter
def staff_attendance_edit_last(resident_id: int):
    return staff_attendance_edit_last_view(resident_id)


@attendance.route("/staff/attendance/resident/<int:resident_id>/print")
@require_login
@require_shelter
def staff_attendance_resident_print(resident_id: int):
    return staff_attendance_resident_print_view(resident_id)


@attendance.route("/staff/attendance/print_today")
@require_login
@require_shelter
def staff_attendance_print_today():
    return staff_attendance_print_today_view()


@attendance.route("/staff/passes/pending")
@require_login
@require_shelter
def staff_passes_pending():
    return staff_passes_pending_view()


@attendance.route("/staff/passes/approved")
@require_login
@require_shelter
def staff_passes_approved():
    return staff_passes_approved_view()


@attendance.route("/staff/passes/<int:pass_id>")
@require_login
@require_shelter
def staff_pass_detail(pass_id: int):
    return staff_pass_detail_view(pass_id)


@attendance.route("/staff/passes/<int:pass_id>/approve", methods=["POST"])
@require_login
@require_shelter
def staff_pass_approve(pass_id: int):
    return staff_pass_approve_view(pass_id)


@attendance.route("/staff/passes/<int:pass_id>/deny", methods=["POST"])
@require_login
@require_shelter
def staff_pass_deny(pass_id: int):
    return staff_pass_deny_view(pass_id)
