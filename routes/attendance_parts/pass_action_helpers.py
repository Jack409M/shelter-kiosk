from __future__ import annotations

import contextlib

from flask import current_app, g

from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import fmt_pretty_date, utcnow_iso
from core.pass_retention import cleanup_deadline_from_expected_back
from core.pass_rules import pass_type_label
from core.sms_sender import send_sms
from routes.attendance_parts.helpers import complete_active_passes


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


def build_approval_sms(pass_row: dict) -> str:
    pass_type_key = _normalized_pass_type(pass_row.get("pass_type"))
    pass_type_text = pass_type_label(pass_type_key)
    first_name = _clean_text(pass_row.get("first_name"))

    if pass_type_key in {"pass", "overnight"}:
        start_text = fmt_pretty_date(pass_row.get("start_at"))
        end_text = fmt_pretty_date(pass_row.get("end_at"))
        return (
            f"{pass_type_text} approved for {first_name}. Start {start_text}. End {end_text}."
        )

    start_date = _clean_text(pass_row.get("start_date"))
    end_date = _clean_text(pass_row.get("end_date"))
    return f"{pass_type_text} approved for {first_name}. Dates: {start_date} to {end_date}."

# rest of file unchanged
