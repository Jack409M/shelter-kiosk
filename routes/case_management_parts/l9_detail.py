from __future__ import annotations

from flask import flash, redirect, render_template, session, url_for

from core.db import db_fetchall, db_fetchone
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    placeholder,
)


def _require_case_manager_access():
    if case_manager_allowed():
        return None
    flash("Case manager access required.", "error")
    return redirect(url_for("attendance.staff_attendance"))


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _load_lifecycle(lifecycle_id: int, shelter: str):
    ph = placeholder()
    return db_fetchone(
        f"""
        SELECT
            l9.id,
            l9.resident_id,
            l9.enrollment_id,
            l9.shelter,
            l9.case_manager_user_id,
            l9.started_by_user_id,
            l9.status,
            l9.participation_status,
            l9.start_date,
            l9.initial_end_date,
            l9.extended_end_date,
            l9.final_end_date,
            l9.extension_granted,
            l9.extension_decision_date,
            l9.apartment_exit_date,
            l9.apartment_exit_reason,
            l9.deactivation_ready,
            l9.deactivated_at,
            l9.deactivated_by_user_id,
            l9.closure_reason,
            l9.notes,
            l9.created_at,
            l9.updated_at,
            r.first_name,
            r.last_name,
            r.resident_code,
            r.is_active
        FROM level9_support_lifecycles l9
        JOIN residents r ON r.id = l9.resident_id
        WHERE l9.id = {ph}
          AND LOWER(TRIM(l9.shelter)) = LOWER(TRIM({ph}))
        LIMIT 1
        """,
        (lifecycle_id, shelter),
    )


def _load_followups(lifecycle_id: int):
    ph = placeholder()
    return db_fetchall(
        f"""
        SELECT
            id,
            support_month_number,
            due_date,
            completed_date,
            status,
            contact_result,
            followup_method,
            summary_notes,
            housing_status,
            employment_status,
            income_status,
            sobriety_status,
            needs_assistance,
            risk_flag,
            next_steps,
            updated_at
        FROM level9_monthly_followups
        WHERE level9_lifecycle_id = {ph}
        ORDER BY support_month_number ASC
        """,
        (lifecycle_id,),
    )


def _load_exit_interviews(lifecycle_id: int):
    ph = placeholder()
    return db_fetchall(
        f"""
        SELECT
            id,
            interview_type,
            target_date,
            completed_date,
            status,
            declined,
            notes,
            updated_at
        FROM level9_exit_interviews
        WHERE level9_lifecycle_id = {ph}
        ORDER BY target_date ASC, interview_type ASC
        """,
        (lifecycle_id,),
    )


def _load_events(lifecycle_id: int):
    ph = placeholder()
    return db_fetchall(
        f"""
        SELECT
            id,
            event_type,
            event_date,
            performed_by_user_id,
            notes,
            created_at
        FROM level9_support_events
        WHERE level9_lifecycle_id = {ph}
        ORDER BY created_at DESC, id DESC
        """,
        (lifecycle_id,),
    )


def l9_detail_view(lifecycle_id: int):
    init_db()

    denied = _require_case_manager_access()
    if denied is not None:
        return denied

    shelter = _current_shelter()
    lifecycle = _load_lifecycle(lifecycle_id, shelter)
    if not lifecycle:
        flash("Level 9 lifecycle not found.", "error")
        return redirect(url_for("case_management.l9_workspace"))

    return render_template(
        "case_management/l9_detail.html",
        lifecycle=lifecycle,
        followups=_load_followups(lifecycle_id),
        exit_interviews=_load_exit_interviews(lifecycle_id),
        events=_load_events(lifecycle_id),
    )
