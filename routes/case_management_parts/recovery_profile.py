"""
Resident identity and resident centered schema logic.
"""

from __future__ import annotations

from flask import current_app, flash, g, redirect, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from db.schema_people import ensure_resident_child_income_supports_table
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import parse_iso_date
from routes.case_management_parts.helpers import parse_money
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql


def _redirect_resident_case(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _redirect_case_index():
    return redirect(url_for("case_management.index"))


def _yes_no_to_bool(value: str | None) -> bool | None:
    normalized = (value or "").strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


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


def _parse_recovery_profile_form() -> dict:
    level_start_date = parse_iso_date(request.form.get("level_start_date"))
    sobriety_date = parse_iso_date(request.form.get("sobriety_date"))
    treatment_graduation_date = parse_iso_date(request.form.get("treatment_graduation_date"))
    current_job_start_date = parse_iso_date(request.form.get("current_job_start_date"))
    continuous_employment_start_date = parse_iso_date(
        request.form.get("continuous_employment_start_date")
    )
    previous_job_end_date = parse_iso_date(request.form.get("previous_job_end_date"))

    return {
        "program_level": clean(request.form.get("program_level")),
        "level_start_date": level_start_date.isoformat() if level_start_date else None,
        "step_current": parse_int(request.form.get("step_current")),
        "sponsor_name": clean(request.form.get("sponsor_name")),
        "sponsor_active": _yes_no_to_bool(request.form.get("sponsor_active")),
        "step_work_active": _yes_no_to_bool(request.form.get("step_work_active")),
        "sobriety_date": sobriety_date.isoformat() if sobriety_date else None,
        "treatment_graduation_date": (
            treatment_graduation_date.isoformat() if treatment_graduation_date else None
        ),
        "drug_of_choice": clean(request.form.get("drug_of_choice")),
        "employment_notes": clean(request.form.get("employment_notes")),
        "employment_status_current": clean(request.form.get("employment_status_current")),
        "employer_name": clean(request.form.get("employer_name")),
        "employment_type_current": clean(request.form.get("employment_type_current")),
        "monthly_income": parse_money(request.form.get("monthly_income")),
        "current_job_start_date": (
            current_job_start_date.isoformat() if current_job_start_date else None
        ),
        "continuous_employment_start_date": (
            continuous_employment_start_date.isoformat()
            if continuous_employment_start_date
            else None
        ),
        "previous_job_end_date": (
            previous_job_end_date.isoformat() if previous_job_end_date else None
        ),
        "upward_job_change": _yes_no_to_bool(request.form.get("upward_job_change")),
        "supervisor_name": clean(request.form.get("supervisor_name")),
        "supervisor_phone": clean(request.form.get("supervisor_phone")),
        "unemployment_reason": clean(request.form.get("unemployment_reason")),
        "job_change_notes": clean(request.form.get("job_change_notes")),
    }


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

    values = _parse_recovery_profile_form()
    _log_recovery_profile_submission(resident_id)
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
