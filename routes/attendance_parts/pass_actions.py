from __future__ import annotations

from typing import Any

from flask import abort, flash, redirect, url_for

from core.audit import log_action
from core.db import db_fetchone
from core.sms_sender import send_sms as send_sms
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

type PassActionResponse = tuple[bool, str, str, str]


def _require_pass_access() -> None:
    if not can_manage_passes():
        abort(403)


def _redirect(target: str, pass_id: int | None = None):
    if pass_id is not None:
        return redirect(url_for(target, pass_id=pass_id), code=302)
    return redirect(url_for(target), code=302)


def _resident_id_or_none(value: Any) -> int | None:
    try:
        resident_id = int(value)
    except (TypeError, ValueError):
        return None

    if resident_id <= 0:
        return None

    return resident_id


def _pending_review_result(pass_row: Any) -> tuple[bool, int | None, str, str]:
    ok, resident_id_raw, pass_type_key_raw, error_message = validate_pending_review_pass(pass_row)
    if not ok:
        return False, None, "", error_message

    resident_id = _resident_id_or_none(resident_id_raw)
    if resident_id is None:
        return False, None, "", "Pass request is missing a valid resident."

    pass_type_key = str(pass_type_key_raw or "").strip().lower()
    if not pass_type_key:
        return False, None, "", "Pass request is missing a valid pass type."

    return True, resident_id, pass_type_key, ""


def _check_in_result(pass_row: Any) -> tuple[bool, int | None, str]:
    ok, resident_id_raw, error_message = validate_check_in_pass(pass_row)
    if not ok:
        return False, None, error_message

    resident_id = _resident_id_or_none(resident_id_raw)
    if resident_id is None:
        return False, None, "Pass is missing a valid resident."

    return True, resident_id, ""


def _load_other_active_approved_pass(
    *,
    resident_id: int,
    shelter: str,
    current_pass_id: int,
) -> dict[str, Any] | None:
    return db_fetchone(
        """
        SELECT id, pass_type, start_at, end_at, start_date, end_date
        FROM resident_passes
        WHERE resident_id = %s
          AND id <> %s
          AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
          AND LOWER(TRIM(status)) = 'approved'
        ORDER BY approved_at DESC, id DESC
        LIMIT 1
        """,
        (resident_id, current_pass_id, shelter),
    )


# -----------------------------------------
# APPROVE
# -----------------------------------------


def approve_pass_request(
    *, pass_id: int, shelter: str, staff_id: Any, staff_name: str
) -> PassActionResponse:
    pass_row = load_pass_for_review(pass_id, shelter)

    ok, resident_id, pass_type_key, error_message = _pending_review_result(pass_row)
    if not ok or resident_id is None:
        return False, "attendance.staff_passes_pending", error_message, "error"

    blocked, restriction_rows = has_active_pass_block(resident_id)
    if blocked:
        first_restriction = restriction_rows[0] if restriction_rows else {}
        label = first_restriction.get("restriction_label") or "disciplinary restriction"
        detail = first_restriction.get("restriction_detail") or ""
        return (
            False,
            "attendance.staff_pass_detail",
            f"Pass cannot be approved because resident is under {label}. {detail}".strip(),
            "error",
        )

    active_pass = _load_other_active_approved_pass(
        resident_id=resident_id,
        shelter=shelter,
        current_pass_id=pass_id,
    )
    if active_pass:
        return (
            False,
            "attendance.staff_passes_pending",
            "Pass cannot be approved because this resident already has an active approved pass. "
            "Check the current pass in before approving another pass.",
            "error",
        )

    apply_pass_approval(
        pass_id=pass_id,
        shelter=shelter,
        resident_id=resident_id,
        pass_type_key=pass_type_key,
        pass_row=pass_row,
        staff_id=staff_id,
        staff_name=staff_name,
    )

    send_approval_sms_if_possible(pass_id, shelter)

    log_action(
        "pass",
        resident_id,
        shelter,
        staff_id,
        "approve",
        {"pass_id": pass_id, "pass_type": pass_type_key},
    )

    return True, "attendance.staff_passes_pending", "Pass request approved.", "ok"


# -----------------------------------------
# DENY
# -----------------------------------------


def deny_pass_request(
    *, pass_id: int, shelter: str, staff_id: Any, staff_name: str
) -> PassActionResponse:
    pass_row = load_pass_for_review(pass_id, shelter)

    ok, resident_id, pass_type_key, error_message = _pending_review_result(pass_row)
    if not ok or resident_id is None:
        return False, "attendance.staff_passes_pending", error_message, "error"

    apply_pass_denial(
        pass_id=pass_id,
        shelter=shelter,
        resident_id=resident_id,
        pass_type_key=pass_type_key,
        staff_id=staff_id,
        staff_name=staff_name,
    )

    log_action(
        "pass",
        resident_id,
        shelter,
        staff_id,
        "deny",
        {"pass_id": pass_id, "pass_type": pass_type_key},
    )

    return True, "attendance.staff_passes_pending", "Pass request denied.", "ok"


# -----------------------------------------
# CHECK IN
# -----------------------------------------


def check_in_pass_return(*, pass_id: int, shelter: str, staff_id: Any) -> PassActionResponse:
    pass_row = load_pass_for_check_in(pass_id, shelter)

    ok, resident_id, error_message = _check_in_result(pass_row)
    if not ok or resident_id is None:
        return False, "attendance.staff_passes_away_now", error_message, "error"

    apply_pass_check_in(
        pass_id=pass_id,
        shelter=shelter,
        resident_id=resident_id,
        staff_id=staff_id,
    )

    log_action(
        "pass",
        resident_id,
        shelter,
        staff_id,
        "check_in",
        {"pass_id": pass_id},
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
    return _redirect(target, pass_id if target == "attendance.staff_pass_detail" else None)


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
