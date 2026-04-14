from __future__ import annotations

from flask import Blueprint, Response, flash, redirect, url_for

from core.auth import can_manage_requests, require_login, require_shelter


staff_portal = Blueprint("staff_portal", __name__)

type RouteResponse = Response | str


def _manage_requests_denied_response() -> Response | None:
    if can_manage_requests():
        return None

    flash("Staff only.", "error")
    return redirect(url_for("auth.staff_home"))


def _redirect_if_denied() -> Response | None:
    return _manage_requests_denied_response()


def _guarded_redirect(target_endpoint: str) -> RouteResponse:
    denied_response = _redirect_if_denied()
    if denied_response is not None:
        return denied_response

    return redirect(url_for(target_endpoint))


def _retired_legacy_action(message: str, redirect_endpoint: str) -> RouteResponse:
    denied_response = _redirect_if_denied()
    if denied_response is not None:
        return denied_response

    flash(message, "error")
    return redirect(url_for(redirect_endpoint))


def _retired_pending_pass_redirect() -> RouteResponse:
    return _retired_legacy_action(
        "Legacy leave approval is retired. Use Pending Pass Requests.",
        "attendance.staff_passes_pending",
    )


def _retired_pending_pass_deny_redirect() -> RouteResponse:
    return _retired_legacy_action(
        "Legacy leave denial is retired. Use Pending Pass Requests.",
        "attendance.staff_passes_pending",
    )


def _retired_check_in_redirect() -> RouteResponse:
    return _retired_legacy_action(
        "Legacy leave check in is retired. Use Attendance or the pass workflow.",
        "attendance.staff_attendance",
    )


def _retired_print_redirect() -> RouteResponse:
    return _retired_legacy_action(
        "Legacy leave print is retired. Open the migrated record in the pass workflow.",
        "attendance.staff_passes_pending",
    )


@staff_portal.route("/staff/leave/pending")
@require_login
@require_shelter
def staff_leave_pending() -> RouteResponse:
    return _guarded_redirect("attendance.staff_passes_pending")


@staff_portal.route("/staff/leave/upcoming")
@require_login
@require_shelter
def staff_leave_upcoming() -> RouteResponse:
    return _guarded_redirect("attendance.staff_passes_approved")


@staff_portal.route("/staff/leave/away-now")
@require_login
@require_shelter
def staff_leave_away_now() -> RouteResponse:
    return _guarded_redirect("attendance.staff_attendance")


@staff_portal.route("/staff/leave/overdue")
@require_login
@require_shelter
def staff_leave_overdue() -> RouteResponse:
    return _guarded_redirect("attendance.staff_attendance")


@staff_portal.route("/staff/leave/<int:req_id>/approve", methods=["POST"])
@require_login
@require_shelter
def staff_leave_approve(req_id: int) -> RouteResponse:
    del req_id
    return _retired_pending_pass_redirect()


@staff_portal.route("/staff/leave/<int:req_id>/deny", methods=["POST"])
@require_login
@require_shelter
def staff_leave_deny(req_id: int) -> RouteResponse:
    del req_id
    return _retired_pending_pass_deny_redirect()


@staff_portal.route("/staff/leave/<int:req_id>/check-in", methods=["POST"])
@require_login
@require_shelter
def staff_leave_check_in(req_id: int) -> RouteResponse:
    del req_id
    return _retired_check_in_redirect()


@staff_portal.get("/staff/leave/<int:req_id>/print")
@require_login
@require_shelter
def staff_leave_print(req_id: int) -> RouteResponse:
    del req_id
    return _retired_print_redirect()
