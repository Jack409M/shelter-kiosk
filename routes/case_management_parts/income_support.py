from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_iso_date
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.intake_income_support import load_intake_income_support
from routes.case_management_parts.intake_income_support import recalculate_intake_income_support
from routes.case_management_parts.intake_income_support import upsert_intake_income_support


def _yes_no_to_bool(value: str | None):
    normalized = (value or "").strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _load_current_enrollment(resident_id: int):
    return fetch_current_enrollment_for_resident(
        resident_id,
        columns="""
            id,
            shelter,
            program_status,
            entry_date,
            exit_date
        """,
    )


def _load_resident_in_scope(resident_id: int, shelter: str):
    ph = placeholder()

    return db_fetchone(
        f"""
        SELECT
            id,
            resident_identifier,
            first_name,
            last_name,
            resident_code,
            shelter,
            is_active,
            employer_name,
            employment_status_current,
            employment_type_current,
            supervisor_name,
            supervisor_phone,
            unemployment_reason,
            employment_notes,
            monthly_income,
            current_job_start_date,
            continuous_employment_start_date,
            previous_job_end_date,
            upward_job_change,
            job_change_notes
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        LIMIT 1
        """,
        (resident_id, shelter),
    )


def _sync_resident_income_snapshot(
    resident_id: int,
    weighted_stable_income,
    employment_status_current,
    employer_name,
    employment_type_current,
    supervisor_name,
    supervisor_phone,
    unemployment_reason,
    employment_notes,
    current_job_start_date,
    previous_job_end_date,
    upward_job_change,
    job_change_notes,
) -> None:
    ph = placeholder()
    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE residents
        SET
            employment_status_current = {ph},
            employer_name = {ph},
            employment_type_current = {ph},
            supervisor_name = {ph},
            supervisor_phone = {ph},
            unemployment_reason = {ph},
            employment_notes = {ph},
            monthly_income = {ph},
            current_job_start_date = {ph},
            previous_job_end_date = {ph},
            upward_job_change = {ph},
            job_change_notes = {ph},
            employment_updated_at = {ph}
        WHERE id = {ph}
        """,
        (
            employment_status_current,
            employer_name,
            employment_type_current,
            supervisor_name,
            supervisor_phone,
            unemployment_reason,
            employment_notes,
            weighted_stable_income,
            current_job_start_date.isoformat() if current_job_start_date else None,
            previous_job_end_date.isoformat() if previous_job_end_date else None,
            upward_job_change,
            job_change_notes,
            now,
            resident_id,
        ),
    )


def income_support_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    shelter = normalize_shelter_name(session.get("shelter"))
    resident = _load_resident_in_scope(resident_id, shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = _load_current_enrollment(resident_id)
    enrollment_id = enrollment["id"] if enrollment else None

    if not enrollment_id:
        flash("Resident does not have an active enrollment record yet.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if request.method == "POST":
        upsert_intake_income_support(enrollment_id, request.form)

        intake_income_support = load_intake_income_support(enrollment_id) or {}
        weighted_stable_income = intake_income_support.get("weighted_stable_income")

        employment_status_current = clean(request.form.get("employment_status_current"))
        employer_name = clean(request.form.get("employer_name"))
        employment_type_current = clean(request.form.get("employment_type_current"))
        supervisor_name = clean(request.form.get("supervisor_name"))
        supervisor_phone = clean(request.form.get("supervisor_phone"))
        unemployment_reason = clean(request.form.get("unemployment_reason"))
        employment_notes = clean(request.form.get("employment_notes"))
        job_change_notes = clean(request.form.get("job_change_notes"))
        current_job_start_date = parse_iso_date(request.form.get("current_job_start_date"))
        previous_job_end_date = parse_iso_date(request.form.get("previous_job_end_date"))
        upward_job_change = _yes_no_to_bool(request.form.get("upward_job_change"))

        _sync_resident_income_snapshot(
            resident_id=resident_id,
            weighted_stable_income=weighted_stable_income,
            employment_status_current=employment_status_current,
            employer_name=employer_name,
            employment_type_current=employment_type_current,
            supervisor_name=supervisor_name,
            supervisor_phone=supervisor_phone,
            unemployment_reason=unemployment_reason,
            employment_notes=employment_notes,
            current_job_start_date=current_job_start_date,
            previous_job_end_date=previous_job_end_date,
            upward_job_change=upward_job_change,
            job_change_notes=job_change_notes,
        )

        flash("Employment and income support updated.", "success")
        return redirect(url_for("case_management.income_support", resident_id=resident_id))

    recalculate_intake_income_support(enrollment_id)
    intake_income_support = load_intake_income_support(enrollment_id) or {}

    total_cash_support = intake_income_support.get("total_cash_support")
    weighted_stable_income = intake_income_support.get("weighted_stable_income")

    if weighted_stable_income not in (None, ""):
        _sync_resident_income_snapshot(
            resident_id=resident_id,
            weighted_stable_income=weighted_stable_income,
            employment_status_current=resident.get("employment_status_current"),
            employer_name=resident.get("employer_name"),
            employment_type_current=resident.get("employment_type_current"),
            supervisor_name=resident.get("supervisor_name"),
            supervisor_phone=resident.get("supervisor_phone"),
            unemployment_reason=resident.get("unemployment_reason"),
            employment_notes=resident.get("employment_notes"),
            current_job_start_date=parse_iso_date(resident.get("current_job_start_date")),
            previous_job_end_date=parse_iso_date(resident.get("previous_job_end_date")),
            upward_job_change=resident.get("upward_job_change"),
            job_change_notes=resident.get("job_change_notes"),
        )
        resident = _load_resident_in_scope(resident_id, shelter)

    return render_template(
        "case_management/income_support.html",
        resident=resident,
        enrollment=enrollment,
        enrollment_id=enrollment_id,
        intake_income_support=intake_income_support,
        total_cash_support=total_cash_support,
        weighted_stable_income=weighted_stable_income,
    )
