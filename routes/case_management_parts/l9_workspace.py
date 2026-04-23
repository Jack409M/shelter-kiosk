from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_fetchall
from core.l9_support_lifecycle import (
    complete_level9_followup,
    complete_level9_lifecycle,
    extend_level9_lifecycle,
)
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    placeholder,
)

CHICAGO_TZ = ZoneInfo("America/Chicago")


def _require_case_manager_access():
    if case_manager_allowed():
        return None
    flash("Case manager access required.", "error")
    return redirect(url_for("attendance.staff_attendance"))


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _current_staff_user_id() -> int | None:
    raw = session.get("staff_user_id")
    try:
        return int(raw)
    except Exception:
        return None


def _today_local():
    return datetime.now(CHICAGO_TZ).date()


def _build_context(shelter: str):
    ph = placeholder()
    today = _today_local()
    month_start = today.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    review_cutoff = today + timedelta(days=14)

    active_rows = db_fetchall(
        f"""
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            l9.id AS lifecycle_id,
            l9.start_date,
            l9.initial_end_date,
            l9.extended_end_date,
            l9.final_end_date,
            l9.status,
            l9.deactivation_ready
        FROM level9_support_lifecycles l9
        JOIN residents r ON r.id = l9.resident_id
        WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM({ph}))
          AND r.is_active = TRUE
          AND l9.status IN ({ph}, {ph})
        ORDER BY r.last_name, r.first_name
        """,
        (shelter, "active", "extended"),
    )

    due_rows = db_fetchall(
        f"""
        SELECT
            f.id,
            r.id AS resident_id,
            r.first_name,
            r.last_name,
            f.support_month_number,
            f.due_date
        FROM level9_monthly_followups f
        JOIN level9_support_lifecycles l9 ON l9.id = f.level9_lifecycle_id
        JOIN residents r ON r.id = l9.resident_id
        WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM({ph}))
          AND r.is_active = TRUE
          AND f.status = {ph}
          AND f.due_date BETWEEN {ph} AND {ph}
        ORDER BY f.due_date ASC, r.last_name, r.first_name
        """,
        (shelter, "pending", month_start.isoformat(), month_end.isoformat()),
    )

    overdue_rows = db_fetchall(
        f"""
        SELECT
            f.id,
            r.id AS resident_id,
            r.first_name,
            r.last_name,
            f.support_month_number,
            f.due_date
        FROM level9_monthly_followups f
        JOIN level9_support_lifecycles l9 ON l9.id = f.level9_lifecycle_id
        JOIN residents r ON r.id = l9.resident_id
        WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM({ph}))
          AND r.is_active = TRUE
          AND f.status = {ph}
          AND f.due_date < {ph}
        ORDER BY f.due_date ASC, r.last_name, r.first_name
        """,
        (shelter, "pending", today.isoformat()),
    )

    review_rows = db_fetchall(
        f"""
        SELECT
            r.id AS resident_id,
            r.first_name,
            r.last_name,
            l9.id AS lifecycle_id,
            l9.initial_end_date,
            l9.status
        FROM level9_support_lifecycles l9
        JOIN residents r ON r.id = l9.resident_id
        WHERE LOWER(TRIM(l9.shelter)) = LOWER(TRIM({ph}))
          AND r.is_active = TRUE
          AND l9.status IN ({ph}, {ph})
          AND l9.initial_end_date BETWEEN {ph} AND {ph}
        ORDER BY l9.initial_end_date ASC, r.last_name, r.first_name
        """,
        (
            shelter,
            "active",
            "extended",
            today.isoformat(),
            review_cutoff.isoformat(),
        ),
    )

    return {
        "active_rows": active_rows or [],
        "due_rows": due_rows or [],
        "overdue_rows": overdue_rows or [],
        "review_rows": review_rows or [],
        "active_count": len(active_rows or []),
        "due_count": len(due_rows or []),
        "overdue_count": len(overdue_rows or []),
        "review_count": len(review_rows or []),
    }


def l9_workspace_view():
    denied = _require_case_manager_access()
    if denied:
        return denied

    init_db()
    shelter = _current_shelter()
    ctx = _build_context(shelter)

    return render_template(
        "case_management/l9_workspace.html",
        shelter=shelter,
        **ctx,
    )


def complete_l9_followup_view(followup_id: int):
    denied = _require_case_manager_access()
    if denied:
        return denied

    shelter = _current_shelter()
    staff_user_id = _current_staff_user_id()

    try:
        complete_level9_followup(
            followup_id=followup_id,
            shelter=shelter,
            completed_by_user_id=staff_user_id,
            contact_result=request.form.get("contact_result"),
            followup_method=request.form.get("followup_method"),
            summary_notes=request.form.get("summary_notes"),
            next_steps=request.form.get("next_steps"),
            housing_status=request.form.get("housing_status"),
            employment_status=request.form.get("employment_status"),
            income_status=request.form.get("income_status"),
            sobriety_status=request.form.get("sobriety_status"),
            needs_assistance=bool(request.form.get("needs_assistance")),
            risk_flag=bool(request.form.get("risk_flag")),
        )
        flash("Follow up completed.", "success")
    except Exception:
        flash("Unable to complete follow up.", "error")

    return redirect(url_for("case_management.l9_workspace"))


def review_l9_lifecycle_view(lifecycle_id: int):
    denied = _require_case_manager_access()
    if denied:
        return denied

    staff_user_id = _current_staff_user_id()
    action = (request.form.get("review_action") or "").strip().lower()

    try:
        if action == "extend":
            extend_level9_lifecycle(
                lifecycle_id=lifecycle_id,
                decided_by_user_id=staff_user_id,
            )
            flash("Level 9 lifecycle extended.", "success")
        elif action == "complete":
            complete_level9_lifecycle(
                lifecycle_id=lifecycle_id,
                decided_by_user_id=staff_user_id,
            )
            flash(
                "Level 9 lifecycle completed and marked ready for deactivation.",
                "success",
            )
        else:
            flash("Invalid lifecycle review action.", "error")
    except Exception:
        flash("Unable to update Level 9 lifecycle.", "error")

    return redirect(url_for("case_management.l9_workspace"))
