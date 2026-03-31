from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import fetch_current_enrollment_id_for_resident
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


def inspection_log_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    ph = placeholder()

    inspection_rows = db_fetchall(
        f"""
        SELECT
            id,
            inspection_date,
            passed,
            notes
        FROM resident_living_area_inspections
        WHERE resident_id = {ph}
        ORDER BY inspection_date DESC, id DESC
        """,
        (resident_id,),
    )

    return render_template(
        "case_management/inspection_log.html",
        resident=resident,
        inspection_rows=inspection_rows,
    )


def add_inspection_log_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    inspection_date = _clean(request.form.get("inspection_date"))
    passed_value = (request.form.get("passed") or "").strip().lower()
    passed = passed_value == "yes"
    notes = _clean(request.form.get("notes"))

    if not inspection_date:
        flash("Inspection date is required.", "error")
        return redirect(url_for("case_management.inspection_log", resident_id=resident_id))

    now = utcnow_iso()
    ph = placeholder()

    db_execute(
        f"""
        INSERT INTO resident_living_area_inspections
        (
            resident_id,
            enrollment_id,
            inspection_date,
            passed,
            inspected_by_staff_user_id,
            notes,
            created_at,
            updated_at
        )
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
        """,
        (
            resident_id,
            resident.get("enrollment_id"),
            inspection_date,
            passed,
            session.get("staff_user_id"),
            notes,
            now,
            now,
        ),
    )

    flash("Inspection entry added.", "success")
    return redirect(url_for("case_management.inspection_log", resident_id=resident_id))


def edit_inspection_log_view(resident_id: int, inspection_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    ph = placeholder()

    inspection_row = db_fetchone(
        f"""
        SELECT
            id,
            resident_id,
            inspection_date,
            passed,
            notes
        FROM resident_living_area_inspections
        WHERE id = {ph}
          AND resident_id = {ph}
        LIMIT 1
        """,
        (inspection_id, resident_id),
    )

    if not inspection_row:
        flash("Inspection entry not found.", "error")
        return redirect(url_for("case_management.inspection_log", resident_id=resident_id))

    if request.method == "GET":
        return render_template(
            "case_management/edit_inspection_log.html",
            resident=resident,
            inspection_row=inspection_row,
        )

    inspection_date = _clean(request.form.get("inspection_date"))
    passed_value = (request.form.get("passed") or "").strip().lower()
    passed = passed_value == "yes"
    notes = _clean(request.form.get("notes"))

    if not inspection_date:
        flash("Inspection date is required.", "error")
        return redirect(
            url_for(
                "case_management.edit_inspection_log",
                resident_id=resident_id,
                inspection_id=inspection_id,
            )
        )

    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE resident_living_area_inspections
        SET
            inspection_date = {ph},
            passed = {ph},
            notes = {ph},
            updated_at = {ph}
        WHERE id = {ph}
          AND resident_id = {ph}
        """,
        (
            inspection_date,
            passed,
            notes,
            now,
            inspection_id,
            resident_id,
        ),
    )

    flash("Inspection entry updated.", "success")
    return redirect(url_for("case_management.inspection_log", resident_id=resident_id))
