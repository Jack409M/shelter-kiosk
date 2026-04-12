from __future__ import annotations

from flask import abort, flash, redirect, url_for

from routes.attendance_parts.helpers import can_manage_passes
from routes.attendance_parts.pass_action_helpers import (
    apply_pass_approval,
    apply_pass_check_in,
    apply_pass_denial,
    load_pass_for_check_in,
    load_pass_for_review,
    send_approval_sms_if_possible,
    validate_check_in_pass,
    validate_pending_review_pass,
)
from routes.attendance_parts.pass_policy import has_active_pass_block


def _require_pass_access():
    if not can_manage_passes():
        abort(403)


def _redirect(target: str, pass_id: int | None = None):
    if pass_id:
        return redirect(url_for(target, pass_id=pass_id))
    return redirect(url_for(target))


# -----------------------------------------
# APPROVE
# -----------------------------------------

def approve_pass_request(*, pass_id: int, shelter: str, staff_id, staff_name: str):
    pass_row = load_pass_for_review(pass_id, shelter)

    ok, resident_id, pass_type_key, error_message = validate_pending_review_pass(pass_row)
    if not ok:
        return False, "attendance.staff_passes_pending", error_message, "error"

    blocked, restriction_rows = has_active_pass_block(int(resident_id or 0))
    if blocked:
        label = restriction_rows[0].get("restriction_label") or "disciplinary restriction"
        detail = restriction_rows[0].get("restriction_detail") or ""
        return (
            False,
            "attendance.staff_pass_detail",
            f"Pass cannot be approved because resident is under {label}. {detail}".strip(),
            "error",
        )

    apply_pass_approval(
        pass_id=pass_id,
        shelter=shelter,
        resident_id=int(resident_id or 0),
        pass_type_key=pass_type_key,
        pass_row=pass_row,
        staff_id=staff_id,
        staff_name=staff_name,
    )

    send_approval_sms_if_possible(pass_id, shelter)

    return True, "attendance.staff_passes_pending", "Pass request approved.", "ok"


# -----------------------------------------
# DENY
# -----------------------------------------

def deny_pass_request(*, pass_id: int, shelter: str, staff_id, staff_name: str):
    pass_row = load_pass_for_review(pass_id, shelter)

    ok, resident_id, pass_type_key, error_message = validate_pending_review_pass(pass_row)
    if not ok:
        return False, "attendance.staff_passes_pending", error_message, "error"

    apply_pass_denial(
        pass_id=pass_id,
        shelter=shelter,
        resident_id=int(resident_id or 0),
        pass_type_key=pass_type_key,
        staff_id=staff_id,
        staff_name=staff_name,
    )

    return True, "attendance.staff_passes_pending", "Pass request denied.", "ok"


# -----------------------------------------
# CHECK IN
# -----------------------------------------

def check_in_pass_return(*, pass_id: int, shelter: str, staff_id):
    pass_row = load_pass_for_check_in(pass_id, shelter)

    ok, resident_id, error_message = validate_check_in_pass(pass_row)
    if not ok:
        return False, "attendance.staff_passes_away_now", error_message, "error"

    apply_pass_check_in(
        pass_id=pass_id,
        shelter=shelter,
        resident_id=int(resident_id or 0),
        staff_id=staff_id,
    )

    return True, "attendance.staff_passes_away_now", "Resident checked in from pass.", "ok"


# -----------------------------------------
# VIEWS
# -----------------------------------------

def staff_pass_approve_view(pass_id: int, action_context):
    _require_pass_access()

    ok, target, message, category = approve_pass_request(
        pass_id=pass_id,
        shelter=action_context.shelter,
        staff_id=action_context.staff_id,
        staff_name=action_context.staff_name,
    )

    flash(message, category)
    return _redirect(target, pass_id)


def staff_pass_deny_view(pass_id: int, action_context):
    _require_pass_access()

    ok, target, message, category = deny_pass_request(
        pass_id=pass_id,
        shelter=action_context.shelter,
        staff_id=action_context.staff_id,
        staff_name=action_context.staff_name,
    )

    flash(message, category)
    return _redirect(target)


def staff_pass_check_in_view(pass_id: int, action_context):
    _require_pass_access()

    ok, target, message, category = check_in_pass_return(
        pass_id=pass_id,
        shelter=action_context.shelter,
        staff_id=action_context.staff_id,
    )

    flash(message, category)
    return _redirect(target)
