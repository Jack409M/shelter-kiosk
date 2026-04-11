from __future__ import annotations

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


def load_staff_pass_detail_context(*, pass_id: int, shelter: str) -> dict | None:
    row = db_fetchone(
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
        WHERE rp.id = %s AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
        """
        if g.get("db_kind") == "pg"
        else
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
        WHERE rp.id = ? AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
        """,
        (pass_id, shelter),
    )

    if not row:
        return None

    p = dict(row)

    detail_row = db_fetchone(
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
        """
        if g.get("db_kind") == "pg"
        else
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
        (pass_id,),
    )

    pass_detail = dict(detail_row) if detail_row else None

    p["start_at_local"] = to_local(p.get("start_at"))
    p["end_at_local"] = to_local(p.get("end_at"))
    p["created_at_local"] = to_local(p.get("created_at"))
    p["pass_type_label"] = pass_type_label(p.get("pass_type"))

    if pass_detail:
        pass_detail["reviewed_at_local"] = to_local(pass_detail.get("reviewed_at"))

    hour_summary = None
    try:
        hour_summary = calculate_prior_week_attendance_hours(int(p["resident_id"]), str(p["shelter"]))
    except Exception:
        hour_summary = None

    resident_profile = load_resident_pass_profile(int(p["resident_id"]))
    resident_level = ""
    sponsor_name = ""
    sponsor_active = None
    step_current = None
    step_work_active = None
    monthly_income = None
    program_start_date = None

    if resident_profile:
        resident_level = str(resident_value(resident_profile, "program_level", 2, "") or "").strip()
        sponsor_name = str(resident_value(resident_profile, "sponsor_name", 3, "") or "").strip()
        sponsor_active = resident_value(resident_profile, "sponsor_active", 4, None)
        step_current = resident_value(resident_profile, "step_current", 5, None)
        step_work_active = resident_value(resident_profile, "step_work_active", 6, None)
        monthly_income = resident_value(resident_profile, "monthly_income", 7, None)
        program_start_date = resident_value(resident_profile, "date_entered", 8, None)

    if pass_detail and pass_detail.get("resident_level"):
        resident_level = str(pass_detail.get("resident_level") or "").strip() or resident_level

    meeting_summary = None
    try:
        meeting_summary = calculate_meeting_progress(
            resident_id=int(p["resident_id"]),
            shelter=str(p["shelter"]),
            program_start_date=program_start_date,
            level_value=resident_level,
        )
    except Exception:
        meeting_summary = None

    policy_check = build_policy_check(p, pass_detail, hour_summary, meeting_summary)

    return {
        "p": p,
        "pass_detail": pass_detail,
        "hour_summary": hour_summary,
        "meeting_summary": meeting_summary,
        "resident_level": resident_level,
        "sponsor_name": sponsor_name,
        "sponsor_active": sponsor_active,
        "step_current": step_current,
        "step_work_active": step_work_active,
        "monthly_income": monthly_income,
        "policy_check": policy_check,
    }
