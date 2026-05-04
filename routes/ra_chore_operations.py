from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, request, session, url_for

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso

ra_chore_operations = Blueprint(
    "ra_chore_operations",
    __name__,
    url_prefix="/staff/shelter-operations",
)

CHORE_BOARD_COMPLETION_ROLES = {"admin", "shelter_director", "ra"}


def _can_update_chore_board_completion() -> bool:
    return session.get("role") in CHORE_BOARD_COMPLETION_ROLES


def _safe_assigned_date() -> str:
    return str(request.form.get("assigned_date") or request.args.get("assigned_date") or "").strip()


def _safe_scroll_y() -> str:
    raw_scroll_y = str(request.form.get("scroll_y") or request.args.get("scroll_y") or "0").strip()
    return raw_scroll_y if raw_scroll_y.isdigit() else "0"


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
            "shelter_operations.chore_board",
            assigned_date=assigned_date,
            scroll_y=scroll_y,
        )
    )
