from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    fetch_current_enrollment_id_for_resident,
    normalize_shelter_name,
    placeholder,
    shelter_equals_sql,
)
from routes.case_management_parts.medications_validation import validate_medication_form


def _resident_case_redirect(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _medications_redirect(resident_id: int):
    return redirect(url_for("case_management.medications", resident_id=resident_id))


def _quick_add_requested() -> bool:
    return (request.form.get("redirect_to") or "").strip().lower() == "resident_case"


def _post_submit_redirect(resident_id: int):
    if _quick_add_requested():
        return _resident_case_redirect(resident_id)
    return _medications_redirect(resident_id)


def _resident_context(resident_id: int):
    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            r.shelter
        FROM residents r
        WHERE r.id = {ph}
          AND {shelter_equals_sql("r.shelter")}
        LIMIT 1
        """,
        (resident_id, shelter),
    )

    if not resident:
        return None

    resident = dict(resident)
    resident["enrollment_id"] = fetch_current_enrollment_id_for_resident(resident_id)
    return resident


def medication_form_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

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
        return _resident_case_redirect(resident_id)

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    data, error = validate_medication_form(request.form)
    if error:
        flash(error, "error")
        return _post_submit_redirect(resident_id)

    now = utcnow_iso()
    ph = placeholder()

    try:
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
                data["medication_name"],
                data["dosage"],
                data["frequency"],
                data["purpose"],
                data["prescribed_by"],
                data["started_on"],
                data["ended_on"],
                data["is_active"],
                data["notes"],
                session.get("staff_user_id"),
                session.get("staff_user_id"),
                now,
                now,
            ),
        )
    except Exception:
        current_app.logger.exception(
            "Failed to add medication for resident_id=%s enrollment_id=%s",
            resident_id,
            resident.get("enrollment_id"),
        )
        flash("Unable to add medication. Please try again or contact an administrator.", "error")
        return _post_submit_redirect(resident_id)

    flash("Medication added.", "success")
    return _resident_case_redirect(resident_id)


def edit_medication_view(resident_id: int, medication_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

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

    data, error = validate_medication_form(request.form)
    if error:
        flash(error, "error")
        return redirect(
            url_for(
                "case_management.edit_medication",
                resident_id=resident_id,
                medication_id=medication_id,
            )
        )

    now = utcnow_iso()

    try:
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
                data["medication_name"],
                data["dosage"],
                data["frequency"],
                data["purpose"],
                data["prescribed_by"],
                data["started_on"],
                data["ended_on"],
                data["is_active"],
                data["notes"],
                session.get("staff_user_id"),
                now,
                medication_id,
                resident_id,
            ),
        )
    except Exception:
        current_app.logger.exception(
            "Failed to edit medication_id=%s resident_id=%s",
            medication_id,
            resident_id,
        )
        flash("Unable to update medication. Please try again or contact an administrator.", "error")
        return redirect(
            url_for(
                "case_management.edit_medication",
                resident_id=resident_id,
                medication_id=medication_id,
            )
        )

    flash("Medication updated.", "success")
    return _resident_case_redirect(resident_id)
