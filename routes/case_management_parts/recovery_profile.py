from __future__ import annotations

from flask import flash, redirect, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import parse_money
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql


def update_recovery_profile_view(resident_id: int):
    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident = db_fetchone(
        f"""
        SELECT
            id,
            step_current
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    current_step = resident.get("step_current")
    new_step = parse_int(request.form.get("step_current"))

    if new_step is not None and (new_step < 1 or new_step > 12):
        flash("Step must be between 1 and 12.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    program_level = (request.form.get("program_level") or "").strip() or None
    sponsor_name = (request.form.get("sponsor_name") or "").strip() or None
    employer_name = (request.form.get("employer_name") or "").strip() or None
    monthly_income = parse_money(request.form.get("monthly_income"))

    step_changed_at = None
    if new_step != current_step:
        step_changed_at = utcnow_iso()

    if step_changed_at is not None:
        db_execute(
            f"""
            UPDATE residents
            SET
                program_level = {ph},
                sponsor_name = {ph},
                employer_name = {ph},
                monthly_income = {ph},
                step_current = {ph},
                step_changed_at = {ph}
            WHERE id = {ph}
            """,
            (
                program_level,
                sponsor_name,
                employer_name,
                monthly_income,
                new_step,
                step_changed_at,
                resident_id,
            ),
        )
    else:
        db_execute(
            f"""
            UPDATE residents
            SET
                program_level = {ph},
                sponsor_name = {ph},
                employer_name = {ph},
                monthly_income = {ph},
                step_current = {ph}
            WHERE id = {ph}
            """,
            (
                program_level,
                sponsor_name,
                employer_name,
                monthly_income,
                new_step,
                resident_id,
            ),
        )

    flash("Recovery profile updated.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
