from __future__ import annotations

from flask import flash, redirect, request, session, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    fetch_current_enrollment_id_for_resident,
    normalize_shelter_name,
    placeholder,
    shelter_equals_sql,
)


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

    existing = db_fetchone(
        f"""
        SELECT id
        FROM program_enrollments
        WHERE resident_id = {ph}
          AND program_status = {ph}
        LIMIT 1
        """,
        (resident_id, "active"),
    )

    if existing:
        flash("Resident already has an active enrollment.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    entry_date = (request.form.get("entry_date") or "").strip()

    if not entry_date:
        flash("Entry date required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    now = utcnow_iso()

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
            created_at,
            updated_at
        )
        VALUES
        (
            {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}
        )
        """,
        (
            resident_id,
            shelter,
            entry_date,
            None,
            "active",
            session.get("staff_user_id"),
            now,
            now,
        ),
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

    goal_text = (request.form.get("goal_text") or "").strip()
    target_date = (request.form.get("target_date") or "").strip()

    if not goal_text:
        flash("Goal text required.", "error")
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

    appointment_date = (request.form.get("appointment_date") or "").strip()
    appointment_type = (request.form.get("appointment_type") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    if not appointment_date:
        flash("Appointment date required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    now = utcnow_iso()

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
            appointment_date,
            notes or None,
            0,
            now,
            now,
        ),
    )

    flash("Appointment scheduled.", "ok")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
