from __future__ import annotations

from datetime import date

from flask import current_app, flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import fetch_current_enrollment_id_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql


def _resident_case_redirect(resident_id: int, anchor: str = "medications"):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id) + f"#{anchor}")


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _parse_iso_date(value: str | None) -> str | None:
    value = _clean(value)
    if not value:
        return None

    try:
        date.fromisoformat(value)
    except ValueError:
        return None

    return value


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


def _validate_medication_form():
    medication_name = _clean(request.form.get("medication_name"))
    dosage = _clean(request.form.get("dosage"))
    frequency = _clean(request.form.get("frequency"))
    purpose = _clean(request.form.get("purpose"))
    prescribed_by = _clean(request.form.get("prescribed_by"))
    started_on_raw = request.form.get("started_on")
    ended_on_raw = request.form.get("ended_on")
    notes = _clean(request.form.get("notes"))
    is_active = (request.form.get("is_active") or "").strip().lower() == "yes"

    started_on = _parse_iso_date(started_on_raw)
    ended_on = _parse_iso_date(ended_on_raw)

    if not medication_name:
        return None, "Medication name is required."

    if started_on_raw and not started_on:
        return None, "Started On must be a valid date."

    if ended_on_raw and not ended_on:
        return None, "Ended On must be a valid date."

    if started_on and ended_on and ended_on < started_on:
        return None, "Ended On cannot be earlier than Started On."

    data = {
        "medication_name": medication_name,
        "dosage": dosage,
        "frequency": frequency,
        "purpose": purpose,
        "prescribed_by": prescribed_by,
        "started_on": started_on,
        "ended_on": ended_on,
        "is_active": is_active,
        "notes": notes,
    }
    return data, None


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

    data, error = _validate_medication_form()
    if error:
        flash(error, "error")
        return redirect(url_for("case_management.medications", resident_id=resident_id))

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
        return redirect(url_for("case_management.medications", resident_id=resident_id))

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

    data, error = _validate_medication_form()
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
