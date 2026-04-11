from __future__ import annotations

from flask import g

from core.audit import log_action
from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import fmt_pretty_date, utcnow_iso
from core.pass_retention import cleanup_deadline_from_expected_back
from core.pass_rules import pass_type_label
from core.sms_sender import send_sms
from routes.attendance_parts.helpers import complete_active_passes
from routes.attendance_parts.pass_policy import has_active_pass_block


def _insert_resident_notification(
    *,
    resident_id: int,
    shelter: str,
    notification_type: str,
    title: str,
    message: str,
    related_pass_id: int | None,
) -> None:
    db_execute(
        """
        INSERT INTO resident_notifications (
            resident_id,
            shelter,
            notification_type,
            title,
            message,
            related_pass_id,
            is_read,
            created_at,
            read_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s)
        """
        if g.get("db_kind") == "pg"
        else
        """
        INSERT INTO resident_notifications (
            resident_id,
            shelter,
            notification_type,
            title,
            message,
            related_pass_id,
            is_read,
            created_at,
            read_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            resident_id,
            shelter,
            notification_type,
            title,
            message,
            related_pass_id,
            utcnow_iso(),
            None,
        ),
    )


def _load_pass_sms_context(pass_id: int, shelter: str):
    return db_fetchone(
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.pass_type,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            r.first_name,
            r.last_name,
            d.resident_phone
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        LEFT JOIN resident_pass_request_details d ON d.pass_id = rp.id
        WHERE rp.id = %s
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.pass_type,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            r.first_name,
            r.last_name,
            d.resident_phone
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        LEFT JOIN resident_pass_request_details d ON d.pass_id = rp.id
        WHERE rp.id = ?
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (pass_id, shelter),
    )


def _build_approval_sms(pass_row: dict) -> str:
    pass_type_key = str(pass_row.get("pass_type") or "").strip().lower()
    pass_type_text = pass_type_label(pass_type_key)
    first_name = str(pass_row.get("first_name") or "").strip()

    if pass_type_key in {"pass", "overnight"}:
        leave_text = fmt_pretty_date(pass_row.get("start_at"))
        return_text = fmt_pretty_date(pass_row.get("end_at"))
        return f"{pass_type_text} approved for {first_name}. Leave {leave_text}. Return {return_text}."
    start_date = str(pass_row.get("start_date") or "").strip()
    end_date = str(pass_row.get("end_date") or "").strip()
    return f"{pass_type_text} approved for {first_name}. Dates: {start_date} to {end_date}."


def approve_pass_request(*, pass_id: int, shelter: str, staff_id, staff_name: str) -> tuple[bool, str, str, str]:
    pass_row = db_fetchone(
        """
        SELECT id, resident_id, shelter, status, pass_type, end_at, end_date
        FROM resident_passes
        WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT id, resident_id, shelter, status, pass_type, end_at, end_date
        FROM resident_passes
        WHERE id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (pass_id, shelter),
    )

    if not pass_row:
        return False, "attendance.staff_passes_pending", "Pass request not found.", "error"

    status = str(pass_row.get("status") or "").strip().lower()
    resident_id = int(pass_row.get("resident_id"))
    pass_type_key = str(pass_row.get("pass_type") or "").strip().lower()

    if status != "pending":
        return False, "attendance.staff_passes_pending", "That pass request is no longer pending.", "error"

    blocked, restriction_rows = has_active_pass_block(resident_id)
    if blocked:
        label = restriction_rows[0].get("restriction_label") or "disciplinary restriction"
        detail = restriction_rows[0].get("restriction_detail") or ""
        return False, "attendance.staff_pass_detail", f"Pass cannot be approved because resident is under {label}. {detail}".strip(), "error"

    now_iso = utcnow_iso()
    delete_after_at = cleanup_deadline_from_expected_back(
        pass_row.get("end_at"),
        pass_row.get("end_date"),
    )

    with db_transaction():
        db_execute(
            """
            UPDATE resident_passes
            SET status = %s,
                approved_by = %s,
                approved_at = %s,
                delete_after_at = %s,
                updated_at = %s
            WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
            """,
            ("approved", staff_id, now_iso, delete_after_at, now_iso, pass_id, shelter),
        )

        db_execute(
            """
            UPDATE resident_pass_request_details
            SET reviewed_by_user_id = %s,
                reviewed_by_name = %s,
                reviewed_at = %s,
                updated_at = %s
            WHERE pass_id = %s
            """,
            (staff_id, staff_name or None, now_iso, now_iso, pass_id),
        )

        _insert_resident_notification(
            resident_id=resident_id,
            shelter=shelter,
            notification_type="pass_approved",
            title=f"{pass_type_label(pass_type_key)} Approved",
            message="Your pass request was approved.",
            related_pass_id=int(pass_id),
        )

    sms_context = _load_pass_sms_context(pass_id, shelter)
    if sms_context:
        phone = str(sms_context.get("resident_phone") or "").strip()
        if phone:
            try:
                send_sms(phone, _build_approval_sms(sms_context))
            except Exception:
                pass

    log_action("pass", resident_id, shelter, staff_id, "approve", f"pass_id={pass_id}")
    return True, "attendance.staff_passes_pending", "Pass request approved.", "ok"


def deny_pass_request(*, pass_id: int, shelter: str, staff_id, staff_name: str) -> tuple[bool, str, str, str]:
    pass_row = db_fetchone(
        """
        SELECT id, resident_id, shelter, status, pass_type
        FROM resident_passes
        WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT id, resident_id, shelter, status, pass_type
        FROM resident_passes
        WHERE id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (pass_id, shelter),
    )

    if not pass_row:
        return False, "attendance.staff_passes_pending", "Pass request not found.", "error"

    status = str(pass_row.get("status") or "").strip().lower()
    resident_id = int(pass_row.get("resident_id"))
    pass_type_key = str(pass_row.get("pass_type") or "").strip().lower()

    if status != "pending":
        return False, "attendance.staff_passes_pending", "That pass request is no longer pending.", "error"

    now_iso = utcnow_iso()

    with db_transaction():
        db_execute(
            """
            UPDATE resident_passes
            SET status = %s,
                approved_by = %s,
                approved_at = %s,
                updated_at = %s
            WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
            """,
            ("denied", staff_id, now_iso, now_iso, pass_id, shelter),
        )

        db_execute(
            """
            UPDATE resident_pass_request_details
            SET reviewed_by_user_id = %s,
                reviewed_by_name = %s,
                reviewed_at = %s,
                updated_at = %s
            WHERE pass_id = %s
            """,
            (staff_id, staff_name or None, now_iso, now_iso, pass_id),
        )

        _insert_resident_notification(
            resident_id=resident_id,
            shelter=shelter,
            notification_type="pass_denied",
            title=f"{pass_type_label(pass_type_key)} Denied",
            message="Your pass request was denied.",
            related_pass_id=int(pass_id),
        )

    log_action("pass", resident_id, shelter, staff_id, "deny", f"pass_id={pass_id}")
    return True, "attendance.staff_passes_pending", "Pass request denied.", "ok"


def check_in_pass_return(*, pass_id: int, shelter: str, staff_id) -> tuple[bool, str, str, str]:
    pass_row = db_fetchone(
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.shelter,
            rp.status,
            rp.pass_type,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            rp.destination,
            r.first_name,
            r.last_name
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.id = %s
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.shelter,
            rp.status,
            rp.pass_type,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            rp.destination,
            r.first_name,
            r.last_name
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.id = ?
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (pass_id, shelter),
    )

    if not pass_row:
        return False, "attendance.staff_passes_away_now", "Pass not found.", "error"

    resident_id = int(pass_row["resident_id"])
    status = str(pass_row.get("status") or "").strip().lower()

    if status != "approved":
        return False, "attendance.staff_passes_away_now", "Only approved passes can be checked back in.", "error"

    db_execute(
        """
        INSERT INTO attendance_events (
            resident_id,
            shelter,
            event_type,
            event_time,
            staff_user_id,
            note,
            expected_back_time,
            destination,
            obligation_start_time,
            obligation_end_time,
            meeting_count,
            meeting_1,
            meeting_2,
            is_recovery_meeting
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            resident_id,
            shelter,
            "check_in",
            utcnow_iso(),
            staff_id,
            "Pass return check in",
            None,
            None,
            None,
            None,
            0,
            None,
            None,
            0,
        ),
    )

    complete_active_passes(resident_id, shelter)

    log_action("pass", resident_id, shelter, staff_id, "check_in", f"pass_id={pass_id}")
    return True, "attendance.staff_passes_away_now", "Resident checked in from pass.", "ok"
