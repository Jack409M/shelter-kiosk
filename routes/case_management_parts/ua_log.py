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


def _resident_case_redirect(resident_id: int, anchor: str = "recovery-snapshot"):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id) + f"#{anchor}")


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


def ua_log_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    ph = placeholder()

    ua_rows = db_fetchall(
        f"""
        SELECT
            id,
            ua_date,
            result,
            substances_detected,
            notes
        FROM resident_ua_log
        WHERE resident_id = {ph}
        ORDER BY ua_date DESC, id DESC
        """,
        (resident_id,),
    )

    return render_template(
        "case_management/ua_log.html",
        resident=resident,
        ua_rows=ua_rows,
    )


def add_ua_log_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    ua_date = _clean(request.form.get("ua_date"))
    result = _clean(request.form.get("result"))
    substances_detected = _clean(request.form.get("substances_detected"))
    notes = _clean(request.form.get("notes"))

    if not ua_date:
        flash("UA date is required.", "error")
        return redirect(url_for("case_management.ua_log", resident_id=resident_id))

    now = utcnow_iso()
    ph = placeholder()

    db_execute(
        f"""
        INSERT INTO resident_ua_log
        (
            resident_id,
            enrollment_id,
            ua_date,
            result,
            substances_detected,
            administered_by_staff_user_id,
            notes,
            created_at,
            updated_at
        )
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
        """,
        (
            resident_id,
            resident.get("enrollment_id"),
            ua_date,
            result,
            substances_detected,
            session.get("staff_user_id"),
            notes,
            now,
            now,
        ),
    )

    flash("UA log entry added.", "success")
    return _resident_case_redirect(resident_id)


def edit_ua_log_view(resident_id: int, ua_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    ph = placeholder()

    ua_row = db_fetchone(
        f"""
        SELECT
            id,
            resident_id,
            ua_date,
            result,
            substances_detected,
            notes
        FROM resident_ua_log
        WHERE id = {ph}
          AND resident_id = {ph}
        LIMIT 1
        """,
        (ua_id, resident_id),
    )

    if not ua_row:
        flash("UA log entry not found.", "error")
        return redirect(url_for("case_management.ua_log", resident_id=resident_id))

    if request.method == "GET":
        return render_template(
            "case_management/edit_ua_log.html",
            resident=resident,
            ua_row=ua_row,
        )

    ua_date = _clean(request.form.get("ua_date"))
    result = _clean(request.form.get("result"))
    substances_detected = _clean(request.form.get("substances_detected"))
    notes = _clean(request.form.get("notes"))

    if not ua_date:
        flash("UA date is required.", "error")
        return redirect(url_for("case_management.edit_ua_log", resident_id=resident_id, ua_id=ua_id))

    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE resident_ua_log
        SET
            ua_date = {ph},
            result = {ph},
            substances_detected = {ph},
            notes = {ph},
            updated_at = {ph}
        WHERE id = {ph}
          AND resident_id = {ph}
        """,
        (
            ua_date,
            result,
            substances_detected,
            notes,
            now,
            ua_id,
            resident_id,
        ),
    )

    flash("UA log entry updated.", "success")
    return _resident_case_redirect(resident_id)
