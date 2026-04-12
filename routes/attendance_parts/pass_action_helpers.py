from __future__ import annotations

from flask import current_app, g

from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import fmt_pretty_date, utcnow_iso
from core.pass_retention import cleanup_deadline_from_expected_back
from core.pass_rules import pass_type_label
from core.sms_sender import send_sms
from routes.attendance_parts.helpers import complete_active_passes


def _sql(pg: str, sqlite: str) -> str:
    return pg if g.get("db_kind") == "pg" else sqlite


def insert_resident_notification(
    *,
    resident_id: int,
    shelter: str,
    notification_type: str,
    title: str,
    message: str,
    related_pass_id: int | None,
) -> None:
    db_execute(
        _sql(
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
            """,
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
        ),
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


def load_pass_for_review(pass_id: int, shelter: str):
    return db_fetchone(
        _sql(
            """
            SELECT id, resident_id, shelter, status, pass_type, end_at, end_date
            FROM resident_passes
            WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
            LIMIT 1
            """,
            """
            SELECT id, resident_id, shelter, status, pass_type, end_at, end_date
            FROM resident_passes
            WHERE id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
            LIMIT 1
            """,
        ),
        (pass_id, shelter),
    )


def load_pass_for_check_in(pass_id: int, shelter: str):
    return db_fetchone(
        _sql(
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
            """,
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
        ),
        (pass_id, shelter),
    )


def load_pass_sms_context(pass_id: int, shelter: str):
    return db_fetchone(
        _sql(
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
            """,
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
        ),
        (pass_id, shelter),
    )


def validate_pending_review_pass(pass_row) -> tuple[bool, int | None, str, str]:
    if not pass_row:
        return False, None, "", "Pass request not found."

    status = str(pass_row.get("status") or "").strip().lower()
    resident_id = int(pass_row.get("resident_id") or 0)
    pass_type_key = str(pass_row.get("pass_type") or "").strip().lower()

    if status != "pending":
        return False, resident_id, pass_type_key, "That pass request is no longer pending."

    return True, resident_id, pass_type_key, ""


def validate_check_in_pass(pass_row) -> tuple[bool, int | None, str]:
    if not pass_row:
        return False, None, "Pass not found."

    resident_id = int(pass_row.get("resident_id") or 0)
    status = str(pass_row.get("status") or "").strip().lower()

    if status != "approved":
        return False, resident_id, "Only approved passes can be checked back in."

    return True, resident_id, ""


def build_approval_sms(pass_row: dict) -> str:
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


def send_approval_sms_if_possible(pass_id: int, shelter: str) -> None:
    sms_context = load_pass_sms_context(pass_id, shelter)
    if not sms_context:
        return

    phone = str(sms_context.get("resident_phone") or "").strip()
    if not phone:
        return

    try:
        send_sms(phone, build_approval_sms(sms_context))
    except Exception:
        try:
            current_app.logger.exception(
                "pass approval sms failed pass_id=%s shelter=%s",
                pass_id,
                shelter,
            )
        except Exception:
            pass


def apply_pass_approval(
    *,
    pass_id: int,
    shelter: str,
    resident_id: int,
    pass_type_key: str,
    pass_row,
    staff_id,
    staff_name: str,
) -> None:
    now_iso = utcnow_iso()
    delete_after_at = cleanup_deadline_from_expected_back(
        pass_row.get("end_at"),
        pass_row.get("end_date"),
    )

    with db_transaction():
        db_execute(
            _sql(
                """
                UPDATE resident_passes
                SET status = %s,
                    approved_by = %s,
                    approved_at = %s,
                    delete_after_at = %s,
                    updated_at = %s
                WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
                """,
                """
                UPDATE resident_passes
                SET status = ?,
                    approved_by = ?,
                    approved_at = ?,
                    delete_after_at = ?,
                    updated_at = ?
                WHERE id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
                """,
            ),
            ("approved", staff_id, now_iso, delete_after_at, now_iso, pass_id, shelter),
        )

        db_execute(
            _sql(
                """
                UPDATE resident_pass_request_details
                SET reviewed_by_user_id = %s,
                    reviewed_by_name = %s,
                    reviewed_at = %s,
                    updated_at = %s
                WHERE pass_id = %s
                """,
                """
                UPDATE resident_pass_request_details
                SET reviewed_by_user_id = ?,
                    reviewed_by_name = ?,
                    reviewed_at = ?,
                    updated_at = ?
                WHERE pass_id = ?
                """,
            ),
            (staff_id, staff_name or None, now_iso, now_iso, pass_id),
        )

        insert_resident_notification(
            resident_id=resident_id,
            shelter=shelter,
            notification_type="pass_approved",
            title=f"{pass_type_label(pass_type_key)} Approved",
            message="Your pass request was approved.",
            related_pass_id=int(pass_id),
        )


def apply_pass_denial(
    *,
    pass_id: int,
    shelter: str,
    resident_id: int,
    pass_type_key: str,
    staff_id,
    staff_name: str,
) -> None:
    now_iso = utcnow_iso()

    with db_transaction():
        db_execute(
            _sql(
                """
                UPDATE resident_passes
                SET status = %s,
                    approved_by = %s,
                    approved_at = %s,
                    updated_at = %s
                WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
                """,
                """
                UPDATE resident_passes
                SET status = ?,
                    approved_by = ?,
                    approved_at = ?,
                    updated_at = ?
                WHERE id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
                """,
            ),
            ("denied", staff_id, now_iso, now_iso, pass_id, shelter),
        )

        db_execute(
            _sql(
                """
                UPDATE resident_pass_request_details
                SET reviewed_by_user_id = %s,
                    reviewed_by_name = %s,
                    reviewed_at = %s,
                    updated_at = %s
                WHERE pass_id = %s
                """,
                """
                UPDATE resident_pass_request_details
                SET reviewed_by_user_id = ?,
                    reviewed_by_name = ?,
                    reviewed_at = ?,
                    updated_at = ?
                WHERE pass_id = ?
                """,
            ),
            (staff_id, staff_name or None, now_iso, now_iso, pass_id),
        )

        insert_resident_notification(
            resident_id=resident_id,
            shelter=shelter,
            notification_type="pass_denied",
            title=f"{pass_type_label(pass_type_key)} Denied",
            message="Your pass request was denied.",
            related_pass_id=int(pass_id),
        )


def apply_pass_check_in(
    *,
    pass_id: int,
    shelter: str,
    resident_id: int,
    staff_id,
) -> None:
    with db_transaction():
        db_execute(
            _sql(
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
            ),
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
