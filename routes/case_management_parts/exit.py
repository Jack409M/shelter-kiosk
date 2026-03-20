from __future__ import annotations

from typing import Any

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    clean,
    normalize_shelter_name,
    parse_iso_date,
    parse_money,
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


def _fetch_resident_and_enrollment(resident_id: int, shelter: str):
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            id,
            resident_identifier,
            first_name,
            last_name,
            resident_code,
            shelter,
            is_active
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        return None, None

    enrollment = db_fetchone(
        f"""
        SELECT
            id,
            resident_id,
            shelter,
            entry_date,
            exit_date,
            program_status
        FROM program_enrollments
        WHERE resident_id = {ph}
          AND {shelter_equals_sql("shelter")}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id, shelter),
    )

    return resident, enrollment


def _load_exit_form_data(enrollment_id: int) -> dict[str, Any]:
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT
            date_graduated,
            date_exit_dwc,
            exit_reason,
            graduate_dwc,
            leave_ama,
            income_at_exit,
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
        "exit_reason": _row_value(row, "exit_reason", 2) or "",
        "graduate_dwc": "yes" if int(_row_value(row, "graduate_dwc", 3) or 0) else "no",
        "leave_ama": "yes" if int(_row_value(row, "leave_ama", 4) or 0) else "no",
        "income_at_exit": _row_value(row, "income_at_exit", 5) or "",
        "education_at_exit": _row_value(row, "education_at_exit", 6) or "",
        "grit_at_exit": _row_value(row, "grit_at_exit", 7) or "",
        "received_car": "yes" if int(_row_value(row, "received_car", 8) or 0) else "no",
        "car_insurance": "yes" if int(_row_value(row, "car_insurance", 9) or 0) else "no",
        "dental_needs_met": "yes" if int(_row_value(row, "dental_needs_met", 10) or 0) else "no",
        "vision_needs_met": "yes" if int(_row_value(row, "vision_needs_met", 11) or 0) else "no",
        "obtained_public_insurance": "yes" if int(_row_value(row, "obtained_public_insurance", 12) or 0) else "no",
        "private_insurance": "yes" if int(_row_value(row, "private_insurance", 13) or 0) else "no",
    }


def _validate_exit_form(form: Any, entry_date: str | None) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {
        "date_graduated": clean(form.get("date_graduated")),
        "date_exit_dwc": clean(form.get("date_exit_dwc")),
        "exit_reason": clean(form.get("exit_reason")),
        "graduate_dwc": clean(form.get("graduate_dwc")),
        "leave_ama": clean(form.get("leave_ama")),
        "income_at_exit": clean(form.get("income_at_exit")),
        "education_at_exit": clean(form.get("education_at_exit")),
        "grit_at_exit": clean(form.get("grit_at_exit")),
        "received_car": clean(form.get("received_car")),
        "car_insurance": clean(form.get("car_insurance")),
        "dental_needs_met": clean(form.get("dental_needs_met")),
        "vision_needs_met": clean(form.get("vision_needs_met")),
        "obtained_public_insurance": clean(form.get("obtained_public_insurance")),
        "private_insurance": clean(form.get("private_insurance")),
    }

    errors: list[str] = []

    exit_date = parse_iso_date(data["date_exit_dwc"])
    if exit_date is None:
        errors.append("Date Exit DWC is required and must be a valid date.")
    data["date_exit_dwc"] = exit_date.isoformat() if exit_date else None

    grad_date = parse_iso_date(data["date_graduated"])
    if data["date_graduated"] and grad_date is None:
        errors.append("Date Graduated must be a valid date.")
    data["date_graduated"] = grad_date.isoformat() if grad_date else None

    if not data["exit_reason"]:
        errors.append("Reason for exit is required.")

    income_at_exit = parse_money(data["income_at_exit"])
    if data["income_at_exit"] and income_at_exit is None:
        errors.append("Current income must be a valid number.")
    data["income_at_exit"] = income_at_exit

    grit_at_exit = parse_money(data["grit_at_exit"])
    if data["grit_at_exit"] and grit_at_exit is None:
        errors.append("Grit at Exit must be a valid number.")
    data["grit_at_exit"] = grit_at_exit

    yes_no_fields = [
        "graduate_dwc",
        "leave_ama",
        "received_car",
        "car_insurance",
        "dental_needs_met",
        "vision_needs_met",
        "obtained_public_insurance",
        "private_insurance",
    ]

    for field_name in yes_no_fields:
        value = data[field_name]
        if value not in {None, "yes", "no"}:
            errors.append(f"{field_name.replace('_', ' ').title()} must be Yes or No.")

    if data["graduate_dwc"] == "yes" and not data["date_graduated"]:
        errors.append("Date Graduated is required when Graduate DWC is Yes.")

    if data["date_graduated"] and data["graduate_dwc"] != "yes":
        errors.append("Graduate DWC must be Yes when Date Graduated is entered.")

    if data["car_insurance"] == "yes" and data["received_car"] != "yes":
        errors.append("Car insurance cannot be Yes unless Received Car is Yes.")

    entry_dt = parse_iso_date(entry_date)
    if entry_dt and exit_date and exit_date < entry_dt:
        errors.append("Date Exit DWC cannot be earlier than the entry date.")

    return data, errors


def _upsert_exit_assessment(enrollment_id: int, data: dict[str, Any]) -> None:
    ph = placeholder()
    now = utcnow_iso()

    existing = db_fetchone(
        f"""
        SELECT id
        FROM exit_assessments
        WHERE enrollment_id = {ph}
        LIMIT 1
        """,
        (enrollment_id,),
    )

    if existing:
        db_execute(
            f"""
            UPDATE exit_assessments
            SET date_graduated = {ph},
                date_exit_dwc = {ph},
                exit_reason = {ph},
                graduate_dwc = {ph},
                leave_ama = {ph},
                income_at_exit = {ph},
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
                data["exit_reason"],
                yes_no_to_int(data["graduate_dwc"]),
                yes_no_to_int(data["leave_ama"]),
                data["income_at_exit"],
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
            exit_reason,
            graduate_dwc,
            leave_ama,
            income_at_exit,
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
            {ph}
        )
        """,
        (
            enrollment_id,
            data["date_graduated"],
            data["date_exit_dwc"],
            data["exit_reason"],
            yes_no_to_int(data["graduate_dwc"]),
            yes_no_to_int(data["leave_ama"]),
            data["income_at_exit"],
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


def _close_enrollment_and_resident(enrollment_id: int, resident_id: int, data: dict[str, Any]) -> None:
    ph = placeholder()
    now = utcnow_iso()

    if data["graduate_dwc"] == "yes":
        program_status = "graduated"
    elif data["leave_ama"] == "yes":
        program_status = "left_ama"
    else:
        program_status = "exited"

    db_execute(
        f"""
        UPDATE program_enrollments
        SET exit_date = {ph},
            program_status = {ph},
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (
            data["date_exit_dwc"],
            program_status,
            now,
            enrollment_id,
        ),
    )

    db_execute(
        f"""
        UPDATE residents
        SET is_active = {ph}
        WHERE id = {ph}
        """,
        (
            False,
            resident_id,
        ),
    )


def exit_assessment_form_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    resident, enrollment = _fetch_resident_and_enrollment(resident_id, shelter)

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

    shelter = normalize_shelter_name(session.get("shelter"))
    resident, enrollment = _fetch_resident_and_enrollment(resident_id, shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    if not enrollment:
        flash("This resident does not have a program enrollment yet.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    entry_date = _row_value(enrollment, "entry_date", 3)
    enrollment_id = _row_value(enrollment, "id", 0)
    validated, errors = _validate_exit_form(request.form, entry_date)

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "case_management/exit_assessment.html",
            resident=resident,
            enrollment=enrollment,
            form_data=request.form.to_dict(flat=True),
        )

    _upsert_exit_assessment(enrollment_id, validated)
    _close_enrollment_and_resident(enrollment_id, resident_id, validated)

    flash("Exit assessment saved.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
