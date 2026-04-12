from __future__ import annotations

from core.audit import log_action
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


def approve_pass_request(*, pass_id: int, shelter: str, staff_id, staff_name: str) -> tuple[bool, str, str, str]:
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

    log_action("pass", resident_id, shelter, staff_id, "approve", f"pass_id={pass_id}")
    return True, "attendance.staff_passes_pending", "Pass request approved.", "ok"


def deny_pass_request(*, pass_id: int, shelter: str, staff_id, staff_name: str) -> tuple[bool, str, str, str]:
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

    log_action("pass", resident_id, shelter, staff_id, "deny", f"pass_id={pass_id}")
    return True, "attendance.staff_passes_pending", "Pass request denied.", "ok"


def check_in_pass_return(*, pass_id: int, shelter: str, staff_id) -> tuple[bool, str, str, str]:
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

    log_action("pass", resident_id, shelter, staff_id, "check_in", f"pass_id={pass_id}")
    return True, "attendance.staff_passes_away_now", "Resident checked in from pass.", "ok"
