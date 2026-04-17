from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, flash, redirect, render_template, url_for

from core.helpers import fmt_dt
from routes.attendance_parts.helpers import can_manage_passes
from routes.attendance_parts.pass_actions import (
    approve_pass_request,
    check_in_pass_return,
    deny_pass_request,
)
from routes.attendance_parts.pass_detail_data import load_staff_pass_detail_context
from routes.attendance_parts.pass_policy import has_active_pass_block as has_active_pass_block
from routes.attendance_parts.pass_queries import (
    fetch_approved_pass_rows,
    fetch_current_pass_rows,
    fetch_pending_pass_rows,
)
from routes.attendance_parts.pass_view_helpers import (
    build_pass_action_redirect_target,
    enrich_pending_pass_rows,
    filter_overdue_pass_rows,
    get_staff_pass_action_context,
    require_manage_passes_role,
)

CHICAGO_TZ = ZoneInfo("America/Chicago")


def staff_passes_pending_view():
    context = require_manage_passes_role()

    rows = fetch_pending_pass_rows(context.shelter)
    processed = enrich_pending_pass_rows(rows)

    return render_template(
        "staff_passes_pending.html",
        rows=processed,
        shelter=context.shelter,
        fmt_dt=fmt_dt,
    )


def staff_passes_approved_view():
    context = require_manage_passes_role()

    rows = fetch_approved_pass_rows(context.shelter)

    return render_template(
        "staff_passes_approved.html",
        rows=rows,
        shelter=context.shelter,
        fmt_dt=fmt_dt,
    )


def staff_passes_away_now_view():
    context = require_manage_passes_role()

    rows = fetch_current_pass_rows(context.shelter)

    return render_template(
        "staff_passes_away_now.html",
        rows=rows,
        shelter=context.shelter,
        fmt_dt=fmt_dt,
    )


def staff_passes_overdue_view():
    context = require_manage_passes_role()

    now_local = datetime.now(CHICAGO_TZ)
    current_rows = fetch_current_pass_rows(context.shelter)
    overdue_rows = filter_overdue_pass_rows(current_rows, now_local)

    return render_template(
        "staff_passes_overdue.html",
        rows=overdue_rows,
        shelter=context.shelter,
        fmt_dt=fmt_dt,
    )


def staff_pass_detail_view(pass_id: int):
    action_context = get_staff_pass_action_context()

    if not can_manage_passes():
        abort(403)

    context = load_staff_pass_detail_context(
        pass_id=pass_id,
        shelter=action_context.shelter,
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
        policy_check=context["policy_check"],
        fmt_dt=fmt_dt,
    )


def staff_pass_approve_view(pass_id: int):
    action_context = get_staff_pass_action_context()

    if not can_manage_passes():
        abort(403)

    ok, target, message, category = approve_pass_request(
        pass_id=pass_id,
        shelter=action_context.shelter,
        staff_id=action_context.staff_id,
        staff_name=action_context.staff_name,
    )
    flash(message, category)

    redirect_target, redirect_kwargs = build_pass_action_redirect_target(target, pass_id=pass_id)
    return redirect(url_for(redirect_target, **redirect_kwargs), code=303)


def staff_pass_deny_view(pass_id: int):
    action_context = get_staff_pass_action_context()

    if not can_manage_passes():
        abort(403)

    ok, target, message, category = deny_pass_request(
        pass_id=pass_id,
        shelter=action_context.shelter,
        staff_id=action_context.staff_id,
        staff_name=action_context.staff_name,
    )
    flash(message, category)
    return redirect(url_for(target), code=303)


def staff_pass_check_in_view(pass_id: int):
    action_context = get_staff_pass_action_context()

    if not can_manage_passes():
        abort(403)

    ok, target, message, category = check_in_pass_return(
        pass_id=pass_id,
        shelter=action_context.shelter,
        staff_id=action_context.staff_id,
    )
    flash(message, category)
    return redirect(url_for(target), code=303)
