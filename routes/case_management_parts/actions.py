from __future__ import annotations

from datetime import datetime

from flask import flash, redirect, request, session, url_for

from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    fetch_current_enrollment_id_for_resident,
    normalize_shelter_name,
    parse_iso_date,
    placeholder,
    resident_has_active_enrollment,
    shelter_equals_sql,
)


def _clean_text(value: str | None) -> str:
    return (value or "").strip()


def _parse_appointment_datetime(value: str | None) -> tuple[datetime | None, str | None]:
    text = _clean_text(value)
    if not text:
        return None, None

    accepted_formats = [
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %I:%M %p",
        "%m/%d/%y %H:%M",
        "%Y-%m-%d",
    ]

    for fmt in accepted_formats:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed, None
        except ValueError:
            continue

    return None, "Appointment date and time must be valid."


def _render_appointment_datetime(value: datetime) -> str:
    if value.hour == 0 and value.minute == 0 and value.second == 0 and value.microsecond == 0:
        return value.strftime("%Y-%m-%d")
    return value.strftime("%Y-%m-%d %H:%M")


def _load_enrollment_context_for_shelter(resident_id: int, shelter: str) -> dict[str, object]:
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            id,
            shelter
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        LIMIT 1
        """,
        (resident_id, shelter),
    )

    enrollment_id = None
    if resident:
        enrollment_id = fetch_current_enrollment_id_for_resident(resident_id)

    return {
        "resident": resident,
        "enrollment_id": enrollment_id,
    }


def _initial_rad_values_for_new_enrollment(shelter: str) -> tuple[int | None, str | None]:
    shelter_key = normalize_shelter_name(shelter)
    if shelter_key == "haven":
        return 0, None
    return None, None


def create_enrollment_view(resident_id: int):
    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident = db_fetchone(
        f"""
        SELECT
            id,
            shelter
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    if resident_has_active_enrollment(resident_id):
        flash("Resident already has an active enrollment.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    entry_date = _clean_text(request.form.get("entry_date"))

    if not entry_date:
        flash("Entry date required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if not parse_iso_date(entry_date):
        flash("Entry date must be a valid date.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    now = utcnow_iso()
    rad_complete, rad_completed_date = _initial_rad_values_for_new_enrollment(shelter)

    with db_transaction():
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
                shelter,
                entry_date,
                None,
                "active",
                session.get("staff_user_id"),
                rad_complete,
                rad_completed_date,
                now,
                now,
            ),
        )

        db_execute(
            f"""
            UPDATE residents
            SET is_active = TRUE
            WHERE id = {ph}
            """,
            (resident_id,),
        )

    flash("Program enrollment started.", "ok")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def add_goal_view(resident_id: int):
    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    context = _load_enrollment_context_for_shelter(resident_id, shelter)
    resident = context["resident"]
    enrollment_id = context["enrollment_id"]

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    if not enrollment_id:
        flash("No active enrollment.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    goal_text = _clean_text(request.form.get("goal_text"))
    target_date = _clean_text(request.form.get("target_date"))

    if not goal_text:
        flash("Goal text required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if target_date and not parse_iso_date(target_date):
        flash("Target date must be a valid date.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    now = utcnow_iso()

    db_execute(
        f"""
        INSERT INTO goals
        (
            enrollment_id,
            goal_text,
            status,
            target_date,
            completed_date,
            created_at,
            updated_at
        )
        VALUES
        (
            {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}
        )
        """,
        (
            enrollment_id,
            goal_text,
            "active",
            target_date or None,
            None,
            now,
            now,
        ),
    )

    flash("Goal added.", "ok")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def add_appointment_view(resident_id: int):
    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    context = _load_enrollment_context_for_shelter(resident_id, shelter)
    resident = context["resident"]
    enrollment_id = context["enrollment_id"]

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    if not enrollment_id:
        flash("No active enrollment.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    appointment_datetime_raw = _clean_text(
        request.form.get("appointment_datetime") or request.form.get("appointment_date")
    )
    appointment_type = _clean_text(request.form.get("appointment_type"))
    notes = _clean_text(request.form.get("notes"))

    if not appointment_datetime_raw:
        flash("Appointment date and time required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    parsed_appointment, appointment_error = _parse_appointment_datetime(appointment_datetime_raw)
    if appointment_error or not parsed_appointment:
        flash(appointment_error or "Appointment date and time must be valid.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    now = utcnow_iso()
    appointment_value = _render_appointment_datetime(parsed_appointment)

    db_execute(
        f"""
        INSERT INTO appointments
        (
            enrollment_id,
            appointment_type,
            appointment_date,
            notes,
            reminder_sent,
            created_at,
            updated_at
        )
        VALUES
        (
            {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}
        )
        """,
        (
            enrollment_id,
            appointment_type or None,
            appointment_value,
            notes or None,
            0,
            now,
            now,
        ),
    )

    flash("Appointment scheduled.", "ok")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
