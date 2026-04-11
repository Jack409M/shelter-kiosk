from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, flash, redirect, render_template, session, url_for

from core.helpers import fmt_dt
from routes.attendance_parts.helpers import can_manage_passes
from routes.attendance_parts.pass_actions import (
    approve_pass_request,
    check_in_pass_return,
    deny_pass_request,
)
from routes.attendance_parts.pass_detail_data import load_staff_pass_detail_context
from routes.attendance_parts.pass_policy import has_active_pass_block
from routes.attendance_parts.pass_queries import (
    fetch_approved_pass_rows,
    fetch_current_pass_rows,
    fetch_pending_pass_rows,
)

CHICAGO_TZ = ZoneInfo("America/Chicago")


def staff_passes_pending_view():
    shelter = session.get("shelter")
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

    context = load_staff_pass_detail_context(
        pass_id=pass_id,
        shelter=str(shelter or "").strip(),
    )
    if not context:
        abort(404)

    return render_template(
        "staff_pass_detail.html",
        p=context["p"],
        pass_detail=context["pass_detail"],
        hour_summary=context["hour_summary"],
        meeting_summary=context["meeting_summary"],
        resident_level=context["resident_level"],
        sponsor_name=context["sponsor_name"],
        sponsor_active=context["sponsor_active"],
        step_current=context["step_current"],
        step_work_active=context["step_work_active"],
        monthly_income=context["monthly_income"],
        policy_check=context["policy_check"],
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
