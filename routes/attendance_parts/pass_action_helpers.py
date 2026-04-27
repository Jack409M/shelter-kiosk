from __future__ import annotations

import contextlib
from typing import Any

from flask import current_app, g

from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import fmt_pretty_date, utcnow_iso
from core.pass_retention import cleanup_deadline_from_expected_back
from core.pass_rules import pass_type_label
from core.sms_sender import send_sms
from routes.attendance_parts.helpers import complete_active_passes


class PassLifecycleTransitionError(RuntimeError):
    """Raised when a guarded pass status transition does not land."""


def _sql(pg: str, sqlite: str) -> str:
    return pg if g.get("db_kind") == "pg" else sqlite


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _normalized_status(value: object) -> str:
    return _clean_text(value).lower()


def _normalized_pass_type(value: object) -> str:
    return _clean_text(value).lower()


def _safe_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None

    return parsed


def _digits_only(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _load_pass_status(pass_id: int, shelter: str, resident_id: int | None = None) -> str:
    if resident_id is None:
        row = db_fetchone(
            _sql(
                """
                SELECT status
                FROM resident_passes
                WHERE id = %s
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
                LIMIT 1
                """,
                """
                SELECT status
                FROM resident_passes
                WHERE id = ?
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
                LIMIT 1
                """,
            ),
            (pass_id, shelter),
        )
    else:
        row = db_fetchone(
            _sql(
                """
                SELECT status
                FROM resident_passes
                WHERE id = %s
                  AND resident_id = %s
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
                LIMIT 1
                """,
                """
                SELECT status
                FROM resident_passes
                WHERE id = ?
                  AND resident_id = ?
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
                LIMIT 1
                """,
            ),
            (pass_id, resident_id, shelter),
        )

    return _normalized_status((row or {}).get("status"))


def _require_landed_status(
    *,
    pass_id: int,
    shelter: str,
    expected_status: str,
    resident_id: int | None = None,
) -> None:
    actual_status = _load_pass_status(pass_id, shelter, resident_id)
    if actual_status != expected_status:
        raise PassLifecycleTransitionError(
            "Pass lifecycle transition failed "
            f"pass_id={pass_id} expected_status={expected_status} actual_status={actual_status or 'missing'}"
        )


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


def load_pass_for_review(pass_id: int, shelter: str) -> dict[str, Any] | None:
    row = db_fetchone(
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
    return dict(row) if row else None


def load_pass_for_check_in(pass_id: int, shelter: str) -> dict[str, Any] | None:
    row = db_fetchone(
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
    return dict(row) if row else None


def load_pass_sms_context(pass_id: int, shelter: str) -> dict[str, Any] | None:
    row = db_fetchone(
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
    return dict(row) if row else None


def validate_pending_review_pass(
    pass_row: dict[str, Any] | None,
) -> tuple[bool, int | None, str, str]:
    if not pass_row:
        return False, None, "", "Pass request not found."

    resident_id = _safe_int(pass_row.get("resident_id"))
    pass_type_key = _normalized_pass_type(pass_row.get("pass_type"))
    status = _normalized_status(pass_row.get("status"))

    if resident_id is None:
        return False, None, pass_type_key, "Pass request is missing a valid resident."

    if not pass_type_key:
        return False, resident_id, "", "Pass request is missing a valid pass type."

    if status != "pending":
        return False, resident_id, pass_type_key, "That pass request is no longer pending."

    return True, resident_id, pass_type_key, ""


def validate_check_in_pass(
    pass_row: dict[str, Any] | None,
) -> tuple[bool, int | None, str]:
    if not pass_row:
        return False, None, "Pass not found."

    resident_id = _safe_int(pass_row.get("resident_id"))
    status = _normalized_status(pass_row.get("status"))

    if resident_id is None:
        return False, None, "Pass is missing a valid resident."

    if status != "approved":
        return False, resident_id, "Only approved passes can be checked back in."

    return True, resident_id, ""


def build_approval_sms(pass_row: dict[str, Any]) -> str:
    pass_type_key = _normalized_pass_type(pass_row.get("pass_type"))
    pass_type_text = pass_type_label(pass_type_key)
    first_name = _clean_text(pass_row.get("first_name"))

    if pass_type_key in {"pass", "overnight"}:
        start_text = fmt_pretty_date(pass_row.get("start_at"))
        end_text = fmt_pretty_date(pass_row.get("end_at"))
        return f"{pass_type_text} approved for {first_name}. Start {start_text}. End {end_text}."

    start_date = _clean_text(pass_row.get("start_date"))
    end_date = _clean_text(pass_row.get("end_date"))
    return f"{pass_type_text} approved for {first_name}. Dates: {start_date} to {end_date}."


def send_approval_sms_if_possible(pass_id: int, shelter: str) -> None:
    sms_context = load_pass_sms_context(pass_id, shelter)
    if not sms_context:
        return

    phone = _clean_text(sms_context.get("resident_phone"))
    if len(_digits_only(phone)) < 10:
        return

    try:
        send_sms(phone, build_approval_sms(sms_context))
    except Exception:
        with contextlib.suppress(Exception):
            current_app.logger.exception(
                "pass approval sms failed pass_id=%s shelter=%s",
                pass_id,
                shelter,
            )


def apply_pass_approval(
    *,
    pass_id: int,
    shelter: str,
    resident_id: int,
    pass_type_key: str,
    pass_row: dict[str, Any],
    staff_id: Any,
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
                WHERE id = %s
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
                  AND LOWER(TRIM(status)) = 'pending'
                """,
                """
                UPDATE resident_passes
                SET status = ?,
                    approved_by = ?,
                    approved_at = ?,
                    delete_after_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
                  AND LOWER(TRIM(status)) = 'pending'
                """,
            ),
            ("approved", staff_id, now_iso, delete_after_at, now_iso, pass_id, shelter),
        )
        _require_landed_status(
            pass_id=pass_id,
            shelter=shelter,
            resident_id=resident_id,
            expected_status="approved",
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
    staff_id: Any,
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
                WHERE id = %s
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
                  AND LOWER(TRIM(status)) = 'pending'
                """,
                """
                UPDATE resident_passes
                SET status = ?,
                    approved_by = ?,
                    approved_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
                  AND LOWER(TRIM(status)) = 'pending'
                """,
            ),
            ("denied", staff_id, now_iso, now_iso, pass_id, shelter),
        )
        _require_landed_status(
            pass_id=pass_id,
            shelter=shelter,
            resident_id=resident_id,
            expected_status="denied",
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
    staff_id: Any,
) -> None:
    with db_transaction():
        pass_row = db_fetchone(
            _sql(
                """
                SELECT end_at, end_date
                FROM resident_passes
                WHERE id = %s
                  AND resident_id = %s
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
                LIMIT 1
                """,
                """
                SELECT end_at, end_date
                FROM resident_passes
                WHERE id = ?
                  AND resident_id = ?
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
                LIMIT 1
                """,
            ),
            (pass_id, resident_id, shelter),
        )
        pass_row = dict(pass_row) if pass_row else None
        now_iso = utcnow_iso()

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
                now_iso,
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

        delete_after_at = cleanup_deadline_from_expected_back(
            pass_row.get("end_at") if pass_row else None,
            pass_row.get("end_date") if pass_row else None,
        )

        db_execute(
            _sql(
                """
                UPDATE resident_passes
                SET status = %s,
                    updated_at = %s,
                    delete_after_at = %s
                WHERE id = %s
                  AND resident_id = %s
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
                  AND LOWER(TRIM(status)) = 'approved'
                """,
                """
                UPDATE resident_passes
                SET status = ?,
                    updated_at = ?,
                    delete_after_at = ?
                WHERE id = ?
                  AND resident_id = ?
                  AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
                  AND LOWER(TRIM(status)) = 'approved'
                """,
            ),
            ("completed", now_iso, delete_after_at, pass_id, resident_id, shelter),
        )
        _require_landed_status(
            pass_id=pass_id,
            shelter=shelter,
            resident_id=resident_id,
            expected_status="completed",
        )

        complete_active_passes(resident_id, shelter)
