from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

ra_chore_operations = Blueprint(
    "ra_chore_operations",
    __name__,
    url_prefix="/staff/shelter-operations",
)

CHORE_BOARD_VIEW_ROLES = {"admin", "shelter_director", "ra"}
CHORE_BOARD_COMPLETION_ROLES = {"admin", "shelter_director", "ra"}


def _clean_role() -> str:
    return str(session.get("role") or "").strip().lower()


def _can_view_chore_board() -> bool:
    return _clean_role() in CHORE_BOARD_VIEW_ROLES


def _can_update_chore_board_completion() -> bool:
    return _clean_role() in CHORE_BOARD_COMPLETION_ROLES


def _week_start_tuesday(date_text: str) -> str:
    base_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    weekday = base_date.weekday()
    days_to_tuesday = (weekday - 1) % 7
    tuesday = base_date - timedelta(days=days_to_tuesday)
    return tuesday.strftime("%Y-%m-%d")


def _week_dates_from_anchor(date_text: str) -> tuple[str, str, list[str]]:
    week_start = _week_start_tuesday(date_text)
    start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
    week_dates = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    week_end = week_dates[-1]
    return week_start, week_end, week_dates


def _safe_assigned_date() -> str:
    return str(request.form.get("assigned_date") or request.args.get("assigned_date") or "").strip()


def _safe_scroll_y() -> str:
    raw_scroll_y = str(request.form.get("scroll_y") or request.args.get("scroll_y") or "0").strip()
    return raw_scroll_y if raw_scroll_y.isdigit() else "0"


@ra_chore_operations.route("/ra-chore-board", methods=["GET"])
@require_login
@require_shelter
def ra_chore_board():
    if not _can_view_chore_board():
        abort(403)

    shelter = session.get("shelter")

    assigned_date = (request.args.get("assigned_date") or "").strip()
    if not assigned_date:
        assigned_date = str(date.today())

    week_start, week_end, week_dates = _week_dates_from_anchor(assigned_date)

    residents = db_fetchall(
        """
        SELECT id, first_name, last_name
        FROM residents
        WHERE shelter = %s AND is_active = TRUE
        ORDER BY last_name, first_name
        """,
        (shelter,),
    )

    chores = db_fetchall(
        """
        SELECT id, name, when_time, default_day
        FROM chore_templates
        WHERE shelter = %s AND active = 1
        ORDER BY
            CASE WHEN when_time IS NULL THEN 1 ELSE 0 END,
            when_time ASC,
            name ASC
        """,
        (shelter,),
    )

    weekly_assignment_rows = db_fetchall(
        """
        SELECT
            ca.id,
            ca.resident_id,
            ca.chore_id,
            ca.assigned_date,
            ca.status,
            r.first_name,
            r.last_name,
            ct.name AS chore_name,
            ct.when_time,
            ct.default_day
        FROM chore_assignments ca
        JOIN residents r ON r.id = ca.resident_id
        JOIN chore_templates ct ON ct.id = ca.chore_id
        WHERE r.shelter = %s
          AND ca.assigned_date BETWEEN %s AND %s
        ORDER BY
            CASE WHEN ct.when_time IS NULL THEN 1 ELSE 0 END,
            ct.when_time ASC,
            ct.name ASC,
            r.last_name ASC,
            r.first_name ASC,
            ca.assigned_date ASC
        """,
        (shelter, week_start, week_end),
    )

    weekly_rows_map: dict[tuple[int, int], dict] = {}

    for row in weekly_assignment_rows:
        row_key = (row["resident_id"], row["chore_id"])

        if row_key not in weekly_rows_map:
            weekly_rows_map[row_key] = {
                "assignment_id": row["id"],
                "resident_id": row["resident_id"],
                "chore_id": row["chore_id"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "chore_name": row["chore_name"],
                "when_label": row["when_time"] or "",
                "default_day": row["default_day"] or "",
                "days": {d: None for d in week_dates},
            }

        weekly_rows_map[row_key]["days"][row["assigned_date"]] = {
            "id": row["id"],
            "status": row["status"],
        }

    weekly_rows = list(weekly_rows_map.values())

    return render_template(
        "shelter_operations/chore_board.html",
        residents=residents,
        chores=chores,
        assigned_date=assigned_date,
        week_start=week_start,
        week_end=week_end,
        week_dates=week_dates,
        weekly_rows=weekly_rows,
    )


@ra_chore_operations.route("/chore-board/<int:assignment_id>/toggle-complete", methods=["POST"])
@require_login
@require_shelter
def toggle_chore_board_completion(assignment_id: int):
    if not _can_update_chore_board_completion():
        abort(403)

    shelter = str(session.get("shelter") or "").strip()
    assigned_date = _safe_assigned_date()
    scroll_y = _safe_scroll_y()

    assignment = db_fetchone(
        """
        SELECT ca.id, ca.status
        FROM chore_assignments ca
        JOIN residents r ON r.id = ca.resident_id
        WHERE ca.id = %s
          AND r.shelter = %s
        LIMIT 1
        """,
        (assignment_id, shelter),
    )

    if not assignment:
        abort(404)

    current_status = str(assignment.get("status") or "assigned").strip().lower()
    next_status = "assigned" if current_status == "completed" else "completed"

    db_execute(
        """
        UPDATE chore_assignments
        SET status = %s,
            updated_at = %s
        WHERE id = %s
        """,
        (next_status, utcnow_iso(), assignment_id),
    )

    log_action(
        "chore_operation",
        assignment_id,
        shelter,
        session.get("staff_user_id"),
        "toggle_completion",
        details={"source": "ra_chore_board", "status": next_status},
    )

    flash("Chore status updated.", "success")
    return redirect(
        url_for(
            "ra_chore_operations.ra_chore_board",
            assigned_date=assigned_date,
            scroll_y=scroll_y,
        )
    )
