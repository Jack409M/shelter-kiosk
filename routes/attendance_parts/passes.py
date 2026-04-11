from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, redirect, render_template, session, url_for, flash

from core.attendance_hours import calculate_prior_week_attendance_hours
from core.helpers import fmt_dt
from core.meeting_progress import calculate_meeting_progress
from core.pass_retention import run_pass_retention_cleanup_for_shelter
from core.pass_rules import pass_type_label
from routes.attendance_parts.helpers import can_manage_passes, to_local
from routes.attendance_parts.pass_actions import (
    approve_pass_request,
    check_in_pass_return,
    deny_pass_request,
)
from routes.attendance_parts.pass_policy import (
    build_policy_check,
    has_active_pass_block,
    load_resident_pass_profile,
    resident_value,
)
from routes.attendance_parts.pass_queries import (
    fetch_approved_pass_rows,
    fetch_current_pass_rows,
    fetch_pending_pass_rows,
)

CHICAGO_TZ = ZoneInfo("America/Chicago")


def staff_passes_pending_view():
    shelter = session.get("shelter")
    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())
    role = session.get("role")

    if role not in {"admin", "shelter_director", "case_manager"}:
        abort(403)

    rows = fetch_pending_pass_rows(str(shelter or "").strip())

    processed = []

    for row in rows:
        blocked, restriction_rows = has_active_pass_block(int(row.get("resident_id") or 0))
        row["has_disciplinary_block"] = blocked
        row["disciplinary_restrictions"] = restriction_rows
        processed.append(row)

    return render_template(
        "staff_passes_pending.html",
        rows=processed,
        shelter=shelter,
        fmt_dt=fmt_dt,
    )


def staff_passes_approved_view():
    shelter = session.get("shelter")
    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())
    role = session.get("role")

    if role not in {"admin", "shelter_director", "case_manager"}:
        abort(403)

    rows = fetch_approved_pass_rows(str(shelter or "").strip())

    return render_template(
        "staff_passes_approved.html",
        rows=rows,
        shelter=shelter,
        fmt_dt=fmt_dt,
    )


def staff_passes_away_now_view():
    shelter = session.get("shelter")
    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())
    role = session.get("role")

    if role not in {"admin", "shelter_director", "case_manager"}:
        abort(403)

    rows = fetch_current_pass_rows(str(shelter or "").strip())

    return render_template(
        "staff_passes_away_now.html",
        rows=rows,
        shelter=shelter,
        fmt_dt=fmt_dt,
    )


def staff_passes_overdue_view():
    shelter = session.get("shelter")
    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())
    role = session.get("role")

    if role not in {"admin", "shelter_director", "case_manager"}:
        abort(403)

    now_local = datetime.now(CHICAGO_TZ)
    overdue_rows: list[dict] = []

    for row in fetch_current_pass_rows(str(shelter or "").strip()):
        expected_back_local = row.get("expected_back_local")
        if expected_back_local and expected_back_local < now_local:
            overdue_rows.append(row)

    return render_template(
        "staff_passes_overdue.html",
        rows=overdue_rows,
        shelter=shelter,
        fmt_dt=fmt_dt,
    )


def staff_pass_detail_view(pass_id: int):
    shelter = session.get("shelter")

    if not can_manage_passes():
        abort(403)

    from flask import g
    from core.db import db_fetchone

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
        abort(404)

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

    return render_template(
        "staff_pass_detail.html",
        p=p,
        pass_detail=pass_detail,
        hour_summary=hour_summary,
        meeting_summary=meeting_summary,
        resident_level=resident_level,
        sponsor_name=sponsor_name,
        sponsor_active=sponsor_active,
        step_current=step_current,
        step_work_active=step_work_active,
        monthly_income=monthly_income,
        policy_check=policy_check,
        fmt_dt=fmt_dt,
    )


def staff_pass_approve_view(pass_id: int):
    shelter = session.get("shelter")
    staff_id = session.get("staff_user_id")
    staff_name = (session.get("username") or "").strip()

    if not can_manage_passes():
        abort(403)

    ok, target, message, category = approve_pass_request(
        pass_id=pass_id,
        shelter=str(shelter or "").strip(),
        staff_id=staff_id,
        staff_name=staff_name,
    )
    flash(message, category)
    return redirect(url_for(target, pass_id=pass_id) if target == "attendance.staff_pass_detail" else url_for(target))


def staff_pass_deny_view(pass_id: int):
    shelter = session.get("shelter")
    staff_id = session.get("staff_user_id")
    staff_name = (session.get("username") or "").strip()

    if not can_manage_passes():
        abort(403)

    ok, target, message, category = deny_pass_request(
        pass_id=pass_id,
        shelter=str(shelter or "").strip(),
        staff_id=staff_id,
        staff_name=staff_name,
    )
    flash(message, category)
    return redirect(url_for(target))


def staff_pass_check_in_view(pass_id: int):
    shelter = session.get("shelter")
    staff_id = session.get("staff_user_id")

    if not can_manage_passes():
        abort(403)

    ok, target, message, category = check_in_pass_return(
        pass_id=pass_id,
        shelter=str(shelter or "").strip(),
        staff_id=staff_id,
    )
    flash(message, category)
    return redirect(url_for(target))
