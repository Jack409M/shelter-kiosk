from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _resident_context(resident_id: int):
    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            r.shelter,
            pe.id AS enrollment_id
        FROM residents r
        LEFT JOIN program_enrollments pe
          ON pe.resident_id = r.id
        WHERE r.id = {ph}
          AND {shelter_equals_sql("r.shelter")}
        ORDER BY pe.id DESC
        LIMIT 1
        """,
        (resident_id, shelter),
    )

    return resident


def medication_form_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    ph = placeholder()

    medications = db_fetchall(
        f"""
        SELECT
            id,
            medication_name,
            dosage,
            frequency,
            purpose,
            prescribed_by,
            started_on,
            ended_on,
            is_active,
            notes
        FROM resident_medications
        WHERE resident_id = {ph}
        ORDER BY
            COALESCE(updated_at, created_at) DESC,
            id DESC
        """,
        (resident_id,),
    )

    return render_template(
        "case_management/medications.html",
        resident=resident,
        medications=medications,
    )


def add_medication_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    medication_name = _clean(request.form.get("medication_name"))
    dosage = _clean(request.form.get("dosage"))
    frequency = _clean(request.form.get("frequency"))
    purpose = _clean(request.form.get("purpose"))
    prescribed_by = _clean(request.form.get("prescribed_by"))
    started_on = _clean(request.form.get("started_on"))
    ended_on = _clean(request.form.get("ended_on"))
    notes = _clean(request.form.get("notes"))
    is_active = 1 if (request.form.get("is_active") or "").strip().lower() == "yes" else 0

    if not medication_name:
        flash("Medication name is required.", "error")
        return redirect(url_for("case_management.medications", resident_id=resident_id))

    now = utcnow_iso()
    ph = placeholder()

    db_execute(
        f"""
        INSERT INTO resident_medications
        (
            resident_id,
            enrollment_id,
            medication_name,
            dosage,
            frequency,
            purpose,
            prescribed_by,
            started_on,
            ended_on,
            is_active,
            notes,
            created_by_staff_user_id,
            updated_by_staff_user_id,
            created_at,
            updated_at
        )
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
        """,
        (
            resident_id,
            resident.get("enrollment_id"),
            medication_name,
            dosage,
            frequency,
            purpose,
            prescribed_by,
            started_on,
            ended_on,
            is_active,
            notes,
            session.get("staff_user_id"),
            session.get("staff_user_id"),
            now,
            now,
        ),
    )

    flash("Medication added.", "success")
    return redirect(url_for("case_management.medications", resident_id=resident_id))


def edit_medication_view(resident_id: int, medication_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    ph = placeholder()

    medication = db_fetchone(
        f"""
        SELECT
            id,
            resident_id,
            medication_name,
            dosage,
            frequency,
            purpose,
            prescribed_by,
            started_on,
            ended_on,
            is_active,
            notes
        FROM resident_medications
        WHERE id = {ph}
          AND resident_id = {ph}
        LIMIT 1
        """,
        (medication_id, resident_id),
    )

    if not medication:
        flash("Medication not found.", "error")
        return redirect(url_for("case_management.medications", resident_id=resident_id))

    if request.method == "GET":
        return render_template(
            "case_management/edit_medication.html",
            resident=resident,
            medication=medication,
        )

    medication_name = _clean(request.form.get("medication_name"))
    dosage = _clean(request.form.get("dosage"))
    frequency = _clean(request.form.get("frequency"))
    purpose = _clean(request.form.get("purpose"))
    prescribed_by = _clean(request.form.get("prescribed_by"))
    started_on = _clean(request.form.get("started_on"))
    ended_on = _clean(request.form.get("ended_on"))
    notes = _clean(request.form.get("notes"))
    is_active = 1 if (request.form.get("is_active") or "").strip().lower() == "yes" else 0

    if not medication_name:
        flash("Medication name is required.", "error")
        return redirect(url_for("case_management.edit_medication", resident_id=resident_id, medication_id=medication_id))

    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE resident_medications
        SET
            medication_name = {ph},
            dosage = {ph},
            frequency = {ph},
            purpose = {ph},
            prescribed_by = {ph},
            started_on = {ph},
            ended_on = {ph},
            is_active = {ph},
            notes = {ph},
            updated_by_staff_user_id = {ph},
            updated_at = {ph}
        WHERE id = {ph}
          AND resident_id = {ph}
        """,
        (
            medication_name,
            dosage,
            frequency,
            purpose,
            prescribed_by,
            started_on,
            ended_on,
            is_active,
            notes,
            session.get("staff_user_id"),
            now,
            medication_id,
            resident_id,
        ),
    )

    flash("Medication updated.", "success")
    return redirect(url_for("case_management.medications", resident_id=resident_id))
