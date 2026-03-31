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


def _clean_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _clean_date_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    return cleaned[:10]


def _normalize_employment_status(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    if normalized in {"employed", "unemployed"}:
        return normalized
    return None


def _normalize_employment_type(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    if normalized in {"full_time", "part_time"}:
        return normalized
    return None


def _normalize_tristate_bool(value: str | None):
    normalized = (value or "").strip().lower()
    if normalized in {"yes", "true", "1", "on"}:
        return True
    if normalized in {"no", "false", "0", "off"}:
        return False
    return None


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
            program_level,
            level_start_date,
            sponsor_name,
            sponsor_active,
            step_current,
            step_work_active,
            employment_status_current,
            employment_type_current,
            employer_name,
            supervisor_name,
            supervisor_phone,
            unemployment_reason,
            employment_notes,
            monthly_income,
            sobriety_date,
            drug_of_choice,
            treatment_graduation_date
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
    parsed_step = parse_int(request.form.get("step_current"))
    new_step = current_step if parsed_step is None else parsed_step

    if new_step is not None and (new_step < 1 or new_step > 12):
        flash("Step must be between 1 and 12.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    program_level = _clean_text(request.form.get("program_level"))
    level_start_date = _clean_date_text(request.form.get("level_start_date"))
    sponsor_name = _clean_text(request.form.get("sponsor_name"))
    sponsor_active = _normalize_tristate_bool(request.form.get("sponsor_active"))
    step_work_active = _normalize_tristate_bool(request.form.get("step_work_active"))

    sobriety_date = _clean_date_text(request.form.get("sobriety_date"))
    drug_of_choice = _clean_text(request.form.get("drug_of_choice"))
    treatment_graduation_date = _clean_date_text(request.form.get("treatment_graduation_date"))

    employer_name = _clean_text(request.form.get("employer_name"))
    employment_status_current = _normalize_employment_status(request.form.get("employment_status_current"))
    employment_type_current = _normalize_employment_type(request.form.get("employment_type_current"))
    supervisor_name = _clean_text(request.form.get("supervisor_name"))
    supervisor_phone = _clean_text(request.form.get("supervisor_phone"))
    unemployment_reason = _clean_text(request.form.get("unemployment_reason"))
    employment_notes = _clean_text(request.form.get("employment_notes"))
    monthly_income = parse_money(request.form.get("monthly_income"))

    if employment_status_current == "unemployed":
        employer_name = None
        supervisor_name = None
        supervisor_phone = None
        employment_type_current = None
    else:
        unemployment_reason = None

    step_changed_at = None
    if new_step != current_step:
        step_changed_at = utcnow_iso()

    employment_changed = (
        employment_status_current != resident.get("employment_status_current")
        or employment_type_current != resident.get("employment_type_current")
        or employer_name != resident.get("employer_name")
        or supervisor_name != resident.get("supervisor_name")
        or supervisor_phone != resident.get("supervisor_phone")
        or unemployment_reason != resident.get("unemployment_reason")
        or employment_notes != resident.get("employment_notes")
        or monthly_income != resident.get("monthly_income")
    )

    employment_updated_at = utcnow_iso() if employment_changed else None

    if step_changed_at is not None and employment_updated_at is not None:
        db_execute(
            f"""
            UPDATE residents
            SET
                program_level = {ph},
                level_start_date = {ph},
                sponsor_name = {ph},
                sponsor_active = {ph},
                sobriety_date = {ph},
                drug_of_choice = {ph},
                treatment_graduation_date = {ph},
                employer_name = {ph},
                employment_status_current = {ph},
                employment_type_current = {ph},
                supervisor_name = {ph},
                supervisor_phone = {ph},
                unemployment_reason = {ph},
                employment_notes = {ph},
                monthly_income = {ph},
                employment_updated_at = {ph},
                step_current = {ph},
                step_work_active = {ph},
                step_changed_at = {ph}
            WHERE id = {ph}
            """,
            (
                program_level,
                level_start_date,
                sponsor_name,
                sponsor_active,
                sobriety_date,
                drug_of_choice,
                treatment_graduation_date,
                employer_name,
                employment_status_current,
                employment_type_current,
                supervisor_name,
                supervisor_phone,
                unemployment_reason,
                employment_notes,
                monthly_income,
                employment_updated_at,
                new_step,
                step_work_active,
                step_changed_at,
                resident_id,
            ),
        )
    elif step_changed_at is not None:
        db_execute(
            f"""
            UPDATE residents
            SET
                program_level = {ph},
                level_start_date = {ph},
                sponsor_name = {ph},
                sponsor_active = {ph},
                sobriety_date = {ph},
                drug_of_choice = {ph},
                treatment_graduation_date = {ph},
                employer_name = {ph},
                employment_status_current = {ph},
                employment_type_current = {ph},
                supervisor_name = {ph},
                supervisor_phone = {ph},
                unemployment_reason = {ph},
                employment_notes = {ph},
                monthly_income = {ph},
                step_current = {ph},
                step_work_active = {ph},
                step_changed_at = {ph}
            WHERE id = {ph}
            """,
            (
                program_level,
                level_start_date,
                sponsor_name,
                sponsor_active,
                sobriety_date,
                drug_of_choice,
                treatment_graduation_date,
                employer_name,
                employment_status_current,
                employment_type_current,
                supervisor_name,
                supervisor_phone,
                unemployment_reason,
                employment_notes,
                monthly_income,
                new_step,
                step_work_active,
                step_changed_at,
                resident_id,
            ),
        )
    elif employment_updated_at is not None:
        db_execute(
            f"""
            UPDATE residents
            SET
                program_level = {ph},
                level_start_date = {ph},
                sponsor_name = {ph},
                sponsor_active = {ph},
                sobriety_date = {ph},
                drug_of_choice = {ph},
                treatment_graduation_date = {ph},
                employer_name = {ph},
                employment_status_current = {ph},
                employment_type_current = {ph},
                supervisor_name = {ph},
                supervisor_phone = {ph},
                unemployment_reason = {ph},
                employment_notes = {ph},
                monthly_income = {ph},
                employment_updated_at = {ph},
                step_current = {ph},
                step_work_active = {ph}
            WHERE id = {ph}
            """,
            (
                program_level,
                level_start_date,
                sponsor_name,
                sponsor_active,
                sobriety_date,
                drug_of_choice,
                treatment_graduation_date,
                employer_name,
                employment_status_current,
                employment_type_current,
                supervisor_name,
                supervisor_phone,
                unemployment_reason,
                employment_notes,
                monthly_income,
                employment_updated_at,
                new_step,
                step_work_active,
                resident_id,
            ),
        )
    else:
        db_execute(
            f"""
            UPDATE residents
            SET
                program_level = {ph},
                level_start_date = {ph},
                sponsor_name = {ph},
                sponsor_active = {ph},
                sobriety_date = {ph},
                drug_of_choice = {ph},
                treatment_graduation_date = {ph},
                employer_name = {ph},
                employment_status_current = {ph},
                employment_type_current = {ph},
                supervisor_name = {ph},
                supervisor_phone = {ph},
                unemployment_reason = {ph},
                employment_notes = {ph},
                monthly_income = {ph},
                step_current = {ph},
                step_work_active = {ph}
            WHERE id = {ph}
            """,
            (
                program_level,
                level_start_date,
                sponsor_name,
                sponsor_active,
                sobriety_date,
                drug_of_choice,
                treatment_graduation_date,
                employer_name,
                employment_status_current,
                employment_type_current,
                supervisor_name,
                supervisor_phone,
                unemployment_reason,
                employment_notes,
                monthly_income,
                new_step,
                step_work_active,
                resident_id,
            ),
        )

    flash("Recovery profile updated.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
