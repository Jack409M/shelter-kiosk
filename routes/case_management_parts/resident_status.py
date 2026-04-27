from __future__ import annotations

from flask import flash, redirect, session, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    placeholder,
    shelter_equals_sql,
)


def _staff_user_id() -> int | None:
    raw_staff_user_id = session.get("staff_user_id")
    if raw_staff_user_id in (None, ""):
        return None

    try:
        return int(raw_staff_user_id)
    except (TypeError, ValueError):
        return None


def deactivate_resident_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT id, shelter, is_active
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        LIMIT 1
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    if not resident.get("is_active"):
        flash("Resident is already inactive.", "ok")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE residents
        SET is_active = FALSE,
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (now, resident_id),
    )

    log_action(
        "resident",
        resident_id,
        resident.get("shelter"),
        _staff_user_id(),
        "resident_deactivated",
        {
            "source": "case_management_workspace",
            "reason": "manual_case_manager_action",
        },
    )

    flash("Resident marked inactive.", "success")
    return redirect(url_for("case_management.index"))
