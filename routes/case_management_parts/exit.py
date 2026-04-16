from __future__ import annotations

import contextlib
from typing import Any

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.exit_validation import validate_exit_form
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    fetch_current_enrollment_for_resident,
    normalize_shelter_name,
    placeholder,
    shelter_equals_sql,
    yes_no_to_int,
)


def _row_value(row: Any, key: str, index: int):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _ensure_exit_assessment_columns() -> None:
    with contextlib.suppress(Exception):
        db_execute(
            "ALTER TABLE exit_assessments ADD COLUMN IF NOT EXISTS graduation_income_snapshot DOUBLE PRECISION"
        )


def _fetch_resident_and_enrollment(resident_id: int):
    ph = placeholder()

    shelter = normalize_shelter_name(session.get("shelter"))
    if not shelter:
        return None, None

    resident = db_fetchone(
        f"""
        SELECT id, resident_identifier, first_name, last_name, resident_code, shelter, is_active
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        return None, None

    enrollment = fetch_current_enrollment_for_resident(
        resident_id,
        shelter=shelter,
        columns="""
            id,
            resident_id,
            shelter,
            entry_date,
            exit_date,
            program_status
        """,
    )

    return resident, enrollment


def _load_exit_form_data(enrollment_id: int) -> dict[str, Any]:
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT
            date_graduated,
            date_exit_dwc,
            exit_category,
            exit_reason,
            graduate_dwc,
            leave_ama,
            leave_amarillo_city,
            leave_amarillo_unknown,
            income_at_exit,
            graduation_income_snapshot,
            education_at_exit,
            grit_at_exit,
            received_car,
            car_insurance,
            dental_needs_met,
            vision_needs_met,
            obtained_public_insurance,
            private_insurance
        FROM exit_assessments
        WHERE enrollment_id = {ph}
        LIMIT 1
        """,
        (enrollment_id,),
    )

    if not row:
        return {}

    return {
        "date_graduated": _row_value(row, "date_graduated", 0) or "",
        "date_exit_dwc": _row_value(row, "date_exit_dwc", 1) or "",
        "exit_category": _row_value(row, "exit_category", 2) or "",
        "exit_reason": _row_value(row, "exit_reason", 3) or "",
        "graduate_dwc": "yes" if int(_row_value(row, "graduate_dwc", 4) or 0) else "no",
        "leave_ama": "yes" if int(_row_value(row, "leave_ama", 5) or 0) else "no",
        "leave_amarillo_city": _row_value(row, "leave_amarillo_city", 6) or "",
        "leave_amarillo_unknown": "yes"
        if int(_row_value(row, "leave_amarillo_unknown", 7) or 0)
        else "no",
        "income_at_exit": _row_value(row, "income_at_exit", 8) or "",
        "graduation_income_snapshot": _row_value(row, "graduation_income_snapshot", 9) or "",
        "education_at_exit": _row_value(row, "education_at_exit", 10) or "",
        "grit_at_exit": _row_value(row, "grit_at_exit", 11) or "",
        "received_car": "yes" if int(_row_value(row, "received_car", 12) or 0) else "no",
        "car_insurance": "yes" if int(_row_value(row, "car_insurance", 13) or 0) else "no",
        "dental_needs_met": "yes"
        if int(_row_value(row, "dental_needs_met", 14) or 0)
        else "no",
        "vision_needs_met": "yes"
        if int(_row_value(row, "vision_needs_met", 15) or 0)
        else "no",
        "obtained_public_insurance": "yes"
        if int(_row_value(row, "obtained_public_insurance", 16) or 0)
        else "no",
        "private_insurance": "yes"
        if int(_row_value(row, "private_insurance", 17) or 0)
        else "no",
    }


def _derive_graduation_income_snapshot(existing_row: Any, data: dict[str, Any]) -> float | None:
    existing_snapshot = None
    if existing_row:
        existing_snapshot = _row_value(existing_row, "graduation_income_snapshot", 1)

    is_graduate = (
        data.get("graduate_dwc") == "yes"
        and data.get("exit_category") == "Successful Completion"
        and data.get("exit_reason") == "Program Graduated"
    )

    if existing_snapshot not in (None, ""):
        return existing_snapshot

    if is_graduate:
        return data.get("income_at_exit")

    return None


def _upsert_exit_assessment(enrollment_id: int, data: dict[str, Any]) -> None:
    ph = placeholder()
    now = utcnow_iso()

    existing = db_fetchone(
        f"SELECT id, graduation_income_snapshot FROM exit_assessments WHERE enrollment_id = {ph}",
        (enrollment_id,),
    )

    graduation_income_snapshot = _derive_graduation_income_snapshot(existing, data)

    if existing:
        db_execute(
            f"""
            UPDATE exit_assessments
            SET date_graduated = {ph},
                date_exit_dwc = {ph},
                exit_category = {ph},
                exit_reason = {ph},
                graduate_dwc = {ph},
                leave_ama = {ph},
                leave_amarillo_city = {ph},
                leave_amarillo_unknown = {ph},
                income_at_exit = {ph},
                graduation_income_snapshot = {ph},
                education_at_exit = {ph},
                grit_at_exit = {ph},
                received_car = {ph},
                car_insurance = {ph},
                dental_needs_met = {ph},
                vision_needs_met = {ph},
                obtained_public_insurance = {ph},
                private_insurance = {ph},
                updated_at = {ph}
            WHERE enrollment_id = {ph}
            """,
            (
                data["date_graduated"],
                data["date_exit_dwc"],
                data["exit_category"],
                data["exit_reason"],
                yes_no_to_int(data["graduate_dwc"]),
                yes_no_to_int(data["leave_ama"]),
                data["leave_amarillo_city"],
                yes_no_to_int(data["leave_amarillo_unknown"]),
                data["income_at_exit"],
                graduation_income_snapshot,
                data["education_at_exit"],
                data["grit_at_exit"],
                yes_no_to_int(data["received_car"]),
                yes_no_to_int(data["car_insurance"]),
                yes_no_to_int(data["dental_needs_met"]),
                yes_no_to_int(data["vision_needs_met"]),
                yes_no_to_int(data["obtained_public_insurance"]),
                yes_no_to_int(data["private_insurance"]),
                now,
                enrollment_id,
            ),
        )
        return

    db_execute(
        f"""
        INSERT INTO exit_assessments
        (
            enrollment_id,
            date_graduated,
            date_exit_dwc,
            exit_category,
            exit_reason,
            graduate_dwc,
            leave_ama,
            leave_amarillo_city,
            leave_amarillo_unknown,
            income_at_exit,
            graduation_income_snapshot,
            education_at_exit,
            grit_at_exit,
            received_car,
            car_insurance,
            dental_needs_met,
            vision_needs_met,
            obtained_public_insurance,
            private_insurance,
            created_at,
            updated_at
        )
        VALUES
        (
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph}
        )
        """,
        (
            enrollment_id,
            data["date_graduated"],
            data["date_exit_dwc"],
            data["exit_category"],
            data["exit_reason"],
            yes_no_to_int(data["graduate_dwc"]),
            yes_no_to_int(data["leave_ama"]),
            data["leave_amarillo_city"],
            yes_no_to_int(data["leave_amarillo_unknown"]),
            data["income_at_exit"],
            graduation_income_snapshot,
            data["education_at_exit"],
            data["grit_at_exit"],
            yes_no_to_int(data["received_car"]),
            yes_no_to_int(data["car_insurance"]),
            yes_no_to_int(data["dental_needs_met"]),
            yes_no_to_int(data["vision_needs_met"]),
            yes_no_to_int(data["obtained_public_insurance"]),
            yes_no_to_int(data["private_insurance"]),
            now,
            now,
        ),
    )


def _close_enrollment_and_resident(
    enrollment_id: int,
    resident_id: int,
    data: dict[str, Any],
) -> None:
    ph = placeholder()
    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE program_enrollments
        SET exit_date = {ph},
            program_status = 'exited',
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (data["date_exit_dwc"], now, enrollment_id),
    )

    active_other = db_fetchone(
        f"""
        SELECT id
        FROM program_enrollments
        WHERE resident_id = {ph}
          AND program_status = 'active'
          AND id <> {ph}
        LIMIT 1
        """,
        (resident_id, enrollment_id),
    )

    if not active_other:
        db_execute(
            f"""
            UPDATE residents
            SET is_active = FALSE
            WHERE id = {ph}
            """,
            (resident_id,),
        )


def exit_assessment_form_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _ensure_exit_assessment_columns()

    resident, enrollment = _fetch_resident_and_enrollment(resident_id)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    if not enrollment:
        flash("This resident does not have a program enrollment yet.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    enrollment_id = _row_value(enrollment, "id", 0)
    form_data = _load_exit_form_data(enrollment_id)

    return render_template(
        "case_management/exit_assessment.html",
        resident=resident,
        enrollment=enrollment,
        form_data=form_data,
    )


def submit_exit_assessment_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _ensure_exit_assessment_columns()

    resident, enrollment = _fetch_resident_and_enrollment(resident_id)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    if not enrollment:
        flash("This resident does not have a program enrollment yet.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    entry_date = _row_value(enrollment, "entry_date", 3)
    enrollment_id = _row_value(enrollment, "id", 0)

    validated, errors = validate_exit_form(request.form, entry_date)

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "case_management/exit_assessment.html",
            resident=resident,
            enrollment=enrollment,
            form_data=request.form.to_dict(),
        )

    _upsert_exit_assessment(enrollment_id, validated)
    _close_enrollment_and_resident(enrollment_id, resident_id, validated)

    flash("Exit assessment saved.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
