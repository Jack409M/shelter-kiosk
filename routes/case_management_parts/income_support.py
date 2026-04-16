from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, session, url_for

from core.db import db_fetchone
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    fetch_current_enrollment_for_resident,
    normalize_shelter_name,
    placeholder,
    shelter_equals_sql,
)
from routes.case_management_parts.income_support_validation import (
    validate_income_support_form,
)
from routes.case_management_parts.intake_income_support import load_intake_income_support
from routes.case_management_parts.income_state_sync import (
    recalculate_and_sync_income_state_atomic,
    save_income_support_and_sync_snapshot_atomic,
)


def _load_current_enrollment(resident_id: int, shelter: str):
    return fetch_current_enrollment_for_resident(
        resident_id,
        shelter=shelter,
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
            monthly_income
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        LIMIT 1
        """,
        (resident_id, shelter),
    )


def _render_income_support_page(
    *,
    resident,
    enrollment,
    enrollment_id: int,
):
    intake_income_support = load_intake_income_support(enrollment_id) or {}
    total_cash_support = intake_income_support.get("total_cash_support")
    weighted_stable_income = intake_income_support.get("weighted_stable_income")

    return render_template(
        "case_management/income_support.html",
        resident=resident,
        enrollment=enrollment,
        enrollment_id=enrollment_id,
        intake_income_support=intake_income_support,
        total_cash_support=total_cash_support,
        weighted_stable_income=weighted_stable_income,
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

    enrollment = _load_current_enrollment(resident_id, shelter)
    enrollment_id = enrollment["id"] if enrollment else None

    if not enrollment_id:
        flash("Resident does not have an active enrollment record yet.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if request.method == "POST":
        values, errors = validate_income_support_form(request.form)

        if errors:
            for error in errors:
                flash(error, "error")
            return _render_income_support_page(
                resident=resident,
                enrollment=enrollment,
                enrollment_id=enrollment_id,
            )

        try:
            save_income_support_and_sync_snapshot_atomic(
                resident_id=resident_id,
                enrollment_id=enrollment_id,
                values=values,
            )
        except Exception as exc:
            current_app.logger.exception(
                "income_support_save_failed resident_id=%s enrollment_id=%s exception_type=%s",
                resident_id,
                enrollment_id,
                type(exc).__name__,
            )
            flash(
                "Unable to save employment and income support. Please try again or contact an administrator.",
                "error",
            )
            return _render_income_support_page(
                resident=resident,
                enrollment=enrollment,
                enrollment_id=enrollment_id,
            )

        flash("Employment and income support updated.", "success")
        return redirect(url_for("case_management.income_support", resident_id=resident_id))

    try:
        recalculate_and_sync_income_state_atomic(
            resident_id=resident_id,
            enrollment_id=enrollment_id,
        )
        resident = _load_resident_in_scope(resident_id, shelter)
    except Exception as exc:
        current_app.logger.exception(
            "income_support_resync_failed resident_id=%s enrollment_id=%s exception_type=%s",
            resident_id,
            enrollment_id,
            type(exc).__name__,
        )
        flash(
            "Employment income totals could not be refreshed right now. Displaying the latest saved data.",
            "error",
        )

    return _render_income_support_page(
        resident=resident,
        enrollment=enrollment,
        enrollment_id=enrollment_id,
    )
