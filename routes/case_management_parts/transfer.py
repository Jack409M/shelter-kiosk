from __future__ import annotations

from datetime import date

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from core.NP_placement_service import PLACEMENT_TYPE_NONE, replace_active_placement
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    fetch_current_enrollment_for_resident,
    normalize_shelter_name,
    parse_iso_date,
    placeholder,
    shelter_equals_sql,
)


def _redirect_resident_case(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))



def _redirect_case_index():
    return redirect(url_for("case_management.index"))



def _row_value(row, key: str, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default



def _fetch_resident_and_enrollment(resident_id: int):
    ph = placeholder()
    shelter = normalize_shelter_name(session.get("shelter"))
    if not shelter:
        return None, None

    resident = db_fetchone(
        f"""
        SELECT id, resident_identifier, first_name, last_name, resident_code, shelter, is_active, program_level
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        LIMIT 1
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
            program_status,
            case_manager_id,
            rad_complete,
            rad_completed_date
        """,
    )
    return resident, enrollment



def _display_shelter_label(value: str) -> str:
    parts = [part for part in value.replace("_", " ").split() if part]
    if not parts:
        return ""
    return " ".join(part.capitalize() for part in parts)



def _load_transfer_shelter_options(current_shelter: str) -> list[dict[str, str]]:
    queries = [
        "SELECT DISTINCT LOWER(TRIM(COALESCE(shelter, ''))) AS shelter FROM shelter_operation_settings",
        "SELECT DISTINCT LOWER(TRIM(COALESCE(shelter, ''))) AS shelter FROM program_enrollments",
        "SELECT DISTINCT LOWER(TRIM(COALESCE(shelter, ''))) AS shelter FROM residents",
    ]

    seen: set[str] = set()
    options: list[dict[str, str]] = []
    current_key = normalize_shelter_name(current_shelter)

    for query in queries:
        try:
            rows = db_fetchall(query)
        except Exception:
            rows = []

        for row in rows or []:
            shelter_value = normalize_shelter_name(_row_value(row, "shelter", ""))
            if not shelter_value or shelter_value == current_key or shelter_value in seen:
                continue
            seen.add(shelter_value)
            options.append(
                {
                    "value": shelter_value,
                    "label": _display_shelter_label(shelter_value),
                }
            )

    options.sort(key=lambda item: item["label"])
    return options



def _validate_transfer_form(enrollment, form) -> tuple[dict[str, str | None], list[str]]:
    current_shelter = normalize_shelter_name(_row_value(enrollment, "shelter", ""))
    entry_date_text = str(_row_value(enrollment, "entry_date", "") or "").strip()

    target_shelter = normalize_shelter_name(form.get("target_shelter"))
    transfer_date_text = str(form.get("transfer_date") or "").strip()

    errors: list[str] = []

    if not target_shelter:
        errors.append("Transfer shelter is required.")
    elif target_shelter == current_shelter:
        errors.append("Transfer shelter must be different from the current shelter.")

    transfer_date = parse_iso_date(transfer_date_text)
    if not transfer_date_text:
        errors.append("Transfer date is required.")
    elif transfer_date is None:
        errors.append("Transfer date must be a valid date.")
    else:
        if transfer_date > date.today():
            errors.append("Transfer date cannot be in the future.")
        entry_date = parse_iso_date(entry_date_text)
        if entry_date and transfer_date < entry_date:
            errors.append("Transfer date cannot be before the current enrollment entry date.")

    return {
        "target_shelter": target_shelter or None,
        "transfer_date": transfer_date.isoformat() if transfer_date else None,
    }, errors



def _release_old_rent_assignment(resident_id: int, current_shelter: str, transfer_date: str, now: str) -> None:
    ph = placeholder()
    db_execute(
        f"""
        UPDATE resident_rent_configs
        SET effective_end_date = {ph},
            updated_at = {ph}
        WHERE resident_id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
          AND COALESCE(effective_end_date, '') = ''
        """,
        (transfer_date, now, resident_id, current_shelter),
    )



def _load_new_transfer_enrollment_id(*, resident_id: int, target_shelter: str, transfer_date: str) -> int | None:
    ph = placeholder()
    row = db_fetchone(
        f"""
        SELECT id
        FROM program_enrollments
        WHERE resident_id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
          AND entry_date = {ph}
          AND program_status = 'active'
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id, target_shelter, transfer_date),
    )
    enrollment_id = _row_value(row, "id")
    return enrollment_id if isinstance(enrollment_id, int) else None



def _apply_transfer(
    *,
    resident_id: int,
    enrollment_id: int,
    current_enrollment,
    target_shelter: str,
    transfer_date: str,
    now: str,
    current_program_level: object = None,
) -> None:
    ph = placeholder()
    current_case_manager_id = _row_value(current_enrollment, "case_manager_id")
    new_case_manager_id = session.get("staff_user_id") or current_case_manager_id
    rad_complete = _row_value(current_enrollment, "rad_complete")
    rad_completed_date = _row_value(current_enrollment, "rad_completed_date")
    current_shelter = normalize_shelter_name(_row_value(current_enrollment, "shelter", ""))

    db_execute(
        f"""
        UPDATE program_enrollments
        SET exit_date = {ph},
            program_status = 'transferred',
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (transfer_date, now, enrollment_id),
    )

    if current_shelter:
        _release_old_rent_assignment(resident_id, current_shelter, transfer_date, now)

    db_execute(
        f"""
        INSERT INTO program_enrollments
        (
            resident_id,
            shelter,
            entry_date,
            exit_date,
            program_status,
            case_manager_id,
            rad_complete,
            rad_completed_date,
            created_at,
            updated_at
        )
        VALUES
        (
            {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}
        )
        """,
        (
            resident_id,
            target_shelter,
            transfer_date,
            None,
            "active",
            new_case_manager_id,
            rad_complete,
            rad_completed_date,
            now,
            now,
        ),
    )

    db_execute(
        f"""
        UPDATE residents
        SET shelter = {ph},
            is_active = TRUE
        WHERE id = {ph}
        """,
        (target_shelter, resident_id),
    )

    new_enrollment_id = _load_new_transfer_enrollment_id(
        resident_id=resident_id,
        target_shelter=target_shelter,
        transfer_date=transfer_date,
    )
    replace_active_placement(
        resident_id=resident_id,
        enrollment_id=new_enrollment_id,
        shelter=target_shelter,
        program_level=current_program_level,
        housing_unit_id=None,
        placement_type=PLACEMENT_TYPE_NONE,
        effective_date=transfer_date,
        change_reason="shelter_transfer",
        note=f"Transferred from {current_shelter} to {target_shelter}.",
        now=now,
    )



def transfer_resident_form_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    resident, enrollment = _fetch_resident_and_enrollment(resident_id)

    if not resident:
        flash("Resident not found.", "error")
        return _redirect_case_index()

    if not enrollment:
        flash("This resident does not have an active enrollment yet.", "error")
        return _redirect_resident_case(resident_id)

    current_shelter = normalize_shelter_name(_row_value(enrollment, "shelter", ""))
    shelter_options = _load_transfer_shelter_options(current_shelter)

    return render_template(
        "case_management/transfer_resident.html",
        resident=resident,
        enrollment=enrollment,
        shelter_options=shelter_options,
        form_data={},
    )



def submit_transfer_resident_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    resident, enrollment = _fetch_resident_and_enrollment(resident_id)

    if not resident:
        flash("Resident not found.", "error")
        return _redirect_case_index()

    if not enrollment:
        flash("This resident does not have an active enrollment yet.", "error")
        return _redirect_resident_case(resident_id)

    enrollment_id = _row_value(enrollment, "id")
    if not isinstance(enrollment_id, int):
        flash("Active enrollment record is invalid.", "error")
        return _redirect_resident_case(resident_id)

    validated, errors = _validate_transfer_form(enrollment, request.form)
    if errors:
        for error in errors:
            flash(error, "error")
        current_shelter = normalize_shelter_name(_row_value(enrollment, "shelter", ""))
        shelter_options = _load_transfer_shelter_options(current_shelter)
        return render_template(
            "case_management/transfer_resident.html",
            resident=resident,
            enrollment=enrollment,
            shelter_options=shelter_options,
            form_data=request.form.to_dict(),
        )

    now = utcnow_iso()

    try:
        with db_transaction():
            _apply_transfer(
                resident_id=resident_id,
                enrollment_id=enrollment_id,
                current_enrollment=enrollment,
                target_shelter=str(validated["target_shelter"]),
                transfer_date=str(validated["transfer_date"]),
                now=now,
                current_program_level=_row_value(resident, "program_level"),
            )
    except Exception:
        flash("Unable to transfer resident.", "error")
        return _redirect_resident_case(resident_id)

    flash("Resident transferred successfully.", "success")
    return _redirect_case_index()
