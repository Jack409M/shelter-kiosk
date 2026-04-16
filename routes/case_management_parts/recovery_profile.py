"""
Resident identity and resident centered schema logic.
"""

from __future__ import annotations

from flask import current_app, flash, g, redirect, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from db.schema_people import ensure_resident_child_income_supports_table
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    placeholder,
    shelter_equals_sql,
)
from routes.case_management_parts.recovery_profile_validation import (
    validate_recovery_profile_form,
)


def _redirect_resident_case(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _redirect_case_index():
    return redirect(url_for("case_management.index"))


def _load_resident_in_scope(resident_id: int):
    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    return db_fetchone(
        f"""
        SELECT
            id,
            shelter,
            first_name,
            last_name
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        LIMIT 1
        """,
        (resident_id, shelter),
    )


def _log_recovery_profile_submission(resident_id: int) -> None:
    current_app.logger.info(
        "Recovery profile submit resident_id=%s employment_type_current=%r current_job_start_date=%r previous_job_end_date=%r upward_job_change=%r job_change_notes=%r sponsor_active=%r step_work_active=%r",
        resident_id,
        request.form.get("employment_type_current"),
        request.form.get("current_job_start_date"),
        request.form.get("previous_job_end_date"),
        request.form.get("upward_job_change"),
        request.form.get("job_change_notes"),
        request.form.get("sponsor_active"),
        request.form.get("step_work_active"),
    )


def _update_recovery_profile(resident_id: int, values: dict, now: str) -> None:
    ph = placeholder()

    db_execute(
        f"""
        UPDATE residents
        SET
            program_level = {ph},
            level_start_date = {ph},
            step_current = {ph},
            sponsor_name = {ph},
            sponsor_active = {ph},
            step_work_active = {ph},
            sobriety_date = {ph},
            treatment_graduation_date = {ph},
            drug_of_choice = {ph},
            employment_notes = {ph},
            employment_status_current = {ph},
            employer_name = {ph},
            employment_type_current = {ph},
            monthly_income = {ph},
            current_job_start_date = {ph},
            continuous_employment_start_date = {ph},
            previous_job_end_date = {ph},
            upward_job_change = {ph},
            supervisor_name = {ph},
            supervisor_phone = {ph},
            unemployment_reason = {ph},
            job_change_notes = {ph},
            employment_updated_at = {ph},
            step_changed_at = {ph}
        WHERE id = {ph}
        """,
        (
            values["program_level"],
            values["level_start_date"],
            values["step_current"],
            values["sponsor_name"],
            values["sponsor_active"],
            values["step_work_active"],
            values["sobriety_date"],
            values["treatment_graduation_date"],
            values["drug_of_choice"],
            values["employment_notes"],
            values["employment_status_current"],
            values["employer_name"],
            values["employment_type_current"],
            values["monthly_income"],
            values["current_job_start_date"],
            values["continuous_employment_start_date"],
            values["previous_job_end_date"],
            values["upward_job_change"],
            values["supervisor_name"],
            values["supervisor_phone"],
            values["unemployment_reason"],
            values["job_change_notes"],
            now,
            now,
            resident_id,
        ),
    )


def update_recovery_profile_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _redirect_resident_case(resident_id)

    ensure_resident_child_income_supports_table(g.get("db_kind"))

    resident = _load_resident_in_scope(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return _redirect_case_index()

    values, errors = validate_recovery_profile_form(request.form)
    _log_recovery_profile_submission(resident_id)

    if errors:
        for error in errors:
            flash(error, "error")
        return _redirect_resident_case(resident_id)

    now = utcnow_iso()

    try:
        _update_recovery_profile(resident_id, values, now)
    except Exception:
        current_app.logger.exception(
            "Failed to save recovery profile for resident_id=%s",
            resident_id,
        )
        flash("Unable to save profile changes.", "error")
        return _redirect_resident_case(resident_id)

    flash("Recovery profile updated.", "success")
    return _redirect_resident_case(resident_id)
