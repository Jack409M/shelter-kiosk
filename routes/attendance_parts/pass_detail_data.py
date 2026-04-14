from __future__ import annotations

from typing import Any

from flask import g

from core.attendance_hours import calculate_prior_week_attendance_hours
from core.db import db_fetchone
from core.meeting_progress import calculate_meeting_progress
from core.pass_rules import pass_type_label
from routes.attendance_parts.helpers import to_local
from routes.attendance_parts.pass_policy import (
    build_policy_check,
    load_resident_pass_profile,
    resident_value,
)


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _safe_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None

    return parsed


def _load_pass_row(pass_id: int, shelter: str) -> dict[str, Any] | None:
    row = db_fetchone(
        _sql(
            """
            SELECT
                rp.id,
                rp.resident_id,
                r.first_name,
                r.last_name,
                rp.shelter,
                rp.pass_type,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.resident_notes,
                rp.staff_notes,
                rp.created_at,
                rp.status
            FROM resident_passes rp
            JOIN residents r ON r.id = rp.resident_id
            WHERE rp.id = %s
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
            """,
            """
            SELECT
                rp.id,
                rp.resident_id,
                r.first_name,
                r.last_name,
                rp.shelter,
                rp.pass_type,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.resident_notes,
                rp.staff_notes,
                rp.created_at,
                rp.status
            FROM resident_passes rp
            JOIN residents r ON r.id = rp.resident_id
            WHERE rp.id = ?
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
            """,
        ),
        (pass_id, shelter),
    )

    if not row:
        return None

    pass_row = dict(row)
    pass_row["start_at_local"] = to_local(pass_row.get("start_at"))
    pass_row["end_at_local"] = to_local(pass_row.get("end_at"))
    pass_row["created_at_local"] = to_local(pass_row.get("created_at"))
    pass_row["pass_type_label"] = pass_type_label(pass_row.get("pass_type"))
    return pass_row


def _load_pass_detail_row(pass_id: int) -> dict[str, Any] | None:
    row = db_fetchone(
        _sql(
            """
            SELECT
                resident_phone,
                request_date,
                resident_level,
                requirements_acknowledged,
                requirements_not_met_explanation,
                reason_for_request,
                who_with,
                destination_address,
                destination_phone,
                companion_names,
                companion_phone_numbers,
                budgeted_amount,
                approved_amount,
                reviewed_by_user_id,
                reviewed_by_name,
                reviewed_at
            FROM resident_pass_request_details
            WHERE pass_id = %s
            LIMIT 1
            """,
            """
            SELECT
                resident_phone,
                request_date,
                resident_level,
                requirements_acknowledged,
                requirements_not_met_explanation,
                reason_for_request,
                who_with,
                destination_address,
                destination_phone,
                companion_names,
                companion_phone_numbers,
                budgeted_amount,
                approved_amount,
                reviewed_by_user_id,
                reviewed_by_name,
                reviewed_at
            FROM resident_pass_request_details
            WHERE pass_id = ?
            LIMIT 1
            """,
        ),
        (pass_id,),
    )

    if not row:
        return None

    detail_row = dict(row)
    detail_row["reviewed_at_local"] = to_local(detail_row.get("reviewed_at"))
    return detail_row


def _load_hour_summary(resident_id: int, shelter: str):
    try:
        return calculate_prior_week_attendance_hours(resident_id, shelter)
    except Exception:
        return None


def _resident_profile_summary(
    resident_id: int,
    pass_detail: dict[str, Any] | None,
) -> dict[str, Any]:
    resident_profile = load_resident_pass_profile(resident_id)

    resident_level = ""
    sponsor_name = ""
    sponsor_active = None
    step_current = None
    step_work_active = None
    monthly_income = None
    program_start_date = None

    if resident_profile:
        resident_level = _clean_text(resident_value(resident_profile, "program_level", 2, ""))
        sponsor_name = _clean_text(resident_value(resident_profile, "sponsor_name", 3, ""))
        sponsor_active = resident_value(resident_profile, "sponsor_active", 4, None)
        step_current = resident_value(resident_profile, "step_current", 5, None)
        step_work_active = resident_value(
            resident_profile,
            "step_work_active",
            6,
            None,
        )
        monthly_income = resident_value(resident_profile, "monthly_income", 7, None)
        program_start_date = resident_value(resident_profile, "date_entered", 8, None)

    if pass_detail and pass_detail.get("resident_level"):
        resident_level = _clean_text(pass_detail.get("resident_level")) or resident_level

    return {
        "resident_level": resident_level,
        "sponsor_name": sponsor_name,
        "sponsor_active": sponsor_active,
        "step_current": step_current,
        "step_work_active": step_work_active,
        "monthly_income": monthly_income,
        "program_start_date": program_start_date,
    }


def _load_meeting_summary(
    *,
    resident_id: int,
    shelter: str,
    program_start_date: Any,
    resident_level: str,
):
    try:
        return calculate_meeting_progress(
            resident_id=resident_id,
            shelter=shelter,
            program_start_date=program_start_date,
            level_value=resident_level,
        )
    except Exception:
        return None


def load_staff_pass_detail_context(*, pass_id: int, shelter: str) -> dict | None:
    pass_row = _load_pass_row(pass_id, shelter)
    if pass_row is None:
        return None

    resident_id = _safe_int(pass_row.get("resident_id"))
    if resident_id is None:
        return None

    pass_detail = _load_pass_detail_row(pass_id)
    hour_summary = _load_hour_summary(resident_id, _clean_text(pass_row.get("shelter")))

    profile_summary = _resident_profile_summary(resident_id, pass_detail)

    meeting_summary = _load_meeting_summary(
        resident_id=resident_id,
        shelter=_clean_text(pass_row.get("shelter")),
        program_start_date=profile_summary["program_start_date"],
        resident_level=profile_summary["resident_level"],
    )

    policy_check = build_policy_check(
        pass_row,
        pass_detail,
        hour_summary,
        meeting_summary,
    )

    return {
        "p": pass_row,
        "pass_detail": pass_detail,
        "hour_summary": hour_summary,
        "meeting_summary": meeting_summary,
        "resident_level": profile_summary["resident_level"],
        "sponsor_name": profile_summary["sponsor_name"],
        "sponsor_active": profile_summary["sponsor_active"],
        "step_current": profile_summary["step_current"],
        "step_work_active": profile_summary["step_work_active"],
        "monthly_income": profile_summary["monthly_income"],
        "policy_check": policy_check,
    }
