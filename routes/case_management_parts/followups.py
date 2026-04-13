from __future__ import annotations

from typing import Any

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    clean,
    fetch_current_enrollment_for_resident,
    normalize_shelter_name,
    parse_iso_date,
    parse_money,
    placeholder,
    shelter_equals_sql,
    yes_no_to_int,
)

ALLOWED_FOLLOWUP_TYPES = {
    "6_month": "6 Month Follow Up",
    "1_year": "1 Year Follow Up",
}


def _row_value(row: Any, key: str, index: int):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _fetch_resident_and_enrollment(resident_id: int):
    shelter = normalize_shelter_name(session.get("shelter"))
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

    enrollment = fetch_current_enrollment_for_resident(
        resident_id,
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


def _load_followup_form_data(enrollment_id: int, followup_type: str) -> dict[str, Any]:
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT
            id,
            followup_date,
            followup_type,
            income_at_followup,
            sober_at_followup,
            notes
        FROM followups
        WHERE enrollment_id = {ph}
          AND followup_type = {ph}
        ORDER BY
            COALESCE(followup_date, '') DESC,
            id DESC
        LIMIT 1
        """,
        (enrollment_id, followup_type),
    )

    if not row:
        return {
            "followup_date": "",
            "followup_type": followup_type,
            "income_at_followup": "",
            "sober_at_followup": "",
            "notes": "",
        }

    return {
        "followup_date": _row_value(row, "followup_date", 1) or "",
        "followup_type": _row_value(row, "followup_type", 2) or followup_type,
        "income_at_followup": _row_value(row, "income_at_followup", 3) or "",
        "sober_at_followup": "yes" if int(_row_value(row, "sober_at_followup", 4) or 0) else "no",
        "notes": _row_value(row, "notes", 5) or "",
    }


def _validate_followup_form(form: Any, followup_type: str) -> tuple[dict[str, Any], list[str]]:
    data = {
        "followup_date": clean(form.get("followup_date")),
        "followup_type": followup_type,
        "income_at_followup": clean(form.get("income_at_followup")),
        "sober_at_followup": clean(form.get("sober_at_followup")),
        "notes": clean(form.get("notes")),
    }

    errors: list[str] = []

    followup_date = parse_iso_date(data["followup_date"])
    if data["followup_date"] and followup_date is None:
        errors.append("Follow up date must be a valid date.")
    data["followup_date"] = followup_date.isoformat() if followup_date else utcnow_iso()[:10]

    income = parse_money(data["income_at_followup"])
    if data["income_at_followup"] and income is None:
        errors.append("Income at Follow Up must be a valid number.")
    if income is not None and income < 0:
        errors.append("Income at Follow Up cannot be negative.")
    data["income_at_followup"] = income

    if data["sober_at_followup"] not in {None, "", "yes", "no"}:
        errors.append("Sober at Follow Up must be Yes or No.")

    return data, errors


def _upsert_followup(enrollment_id: int, data: dict[str, Any]) -> None:
    ph = placeholder()
    now = utcnow_iso()

    existing = db_fetchone(
        f"""
        SELECT id
        FROM followups
        WHERE enrollment_id = {ph}
          AND followup_type = {ph}
          AND followup_date = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id, data["followup_type"], data["followup_date"]),
    )

    if existing:
        existing_id = existing["id"] if isinstance(existing, dict) else existing[0]

        db_execute(
            f"""
            UPDATE followups
            SET followup_date = {ph},
                income_at_followup = {ph},
                sober_at_followup = {ph},
                notes = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                data["followup_date"],
                data["income_at_followup"],
                yes_no_to_int(data["sober_at_followup"]),
                data["notes"],
                now,
                existing_id,
            ),
        )
        return

    db_execute(
        f"""
        INSERT INTO followups
        (
            enrollment_id,
            followup_date,
            followup_type,
            income_at_followup,
            sober_at_followup,
            notes,
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
            {ph}
        )
        """,
        (
            enrollment_id,
            data["followup_date"],
            data["followup_type"],
            data["income_at_followup"],
            yes_no_to_int(data["sober_at_followup"]),
            data["notes"],
            now,
            now,
        ),
    )


def followup_form_view(resident_id: int, followup_type: str):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    if followup_type not in ALLOWED_FOLLOWUP_TYPES:
        flash("Invalid follow up type.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    init_db()

    resident, enrollment = _fetch_resident_and_enrollment(resident_id)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    if not enrollment:
        flash("Resident does not have an enrollment record.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]
    form_data = _load_followup_form_data(enrollment_id, followup_type)

    return render_template(
        "case_management/followup_assessment.html",
        resident=resident,
        enrollment=enrollment,
        enrollment_id=enrollment_id,
        followup_type=followup_type,
        followup_type_label=ALLOWED_FOLLOWUP_TYPES[followup_type],
        form_data=form_data,
    )


def submit_followup_view(resident_id: int, followup_type: str):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    if followup_type not in ALLOWED_FOLLOWUP_TYPES:
        flash("Invalid follow up type.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    init_db()

    resident, enrollment = _fetch_resident_and_enrollment(resident_id)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    if not enrollment:
        flash("Resident does not have an enrollment record.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]

    data, errors = _validate_followup_form(request.form, followup_type)

    if errors:
        for error in errors:
            flash(error, "error")

        return render_template(
            "case_management/followup_assessment.html",
            resident=resident,
            enrollment=enrollment,
            enrollment_id=enrollment_id,
            followup_type=followup_type,
            followup_type_label=ALLOWED_FOLLOWUP_TYPES[followup_type],
            form_data=data,
        )

    _upsert_followup(enrollment_id, data)

    flash(f"{ALLOWED_FOLLOWUP_TYPES[followup_type]} saved successfully.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
