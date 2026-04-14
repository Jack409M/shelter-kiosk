from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

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


def _resident_case_redirect(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


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


def budget_sessions_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    ph = placeholder()

    budget_rows = db_fetchall(
        f"""
        SELECT
            id,
            session_date,
            notes
        FROM resident_budget_sessions
        WHERE resident_id = {ph}
        ORDER BY session_date DESC, id DESC
        """,
        (resident_id,),
    )

    return render_template(
        "case_management/budget_sessions.html",
        resident=resident,
        budget_rows=budget_rows,
    )


def add_budget_session_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    session_date = _clean(request.form.get("session_date"))
    notes = _clean(request.form.get("notes"))

    if not session_date:
        flash("Budget session date is required.", "error")
        return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))

    now = utcnow_iso()
    ph = placeholder()

    db_execute(
        f"""
        INSERT INTO resident_budget_sessions
        (
            resident_id,
            enrollment_id,
            session_date,
            staff_user_id,
            notes,
            created_at,
            updated_at
        )
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})
        """,
        (
            resident_id,
            resident.get("enrollment_id"),
            session_date,
            session.get("staff_user_id"),
            notes,
            now,
            now,
        ),
    )

    flash("Budget session added.", "success")
    return _resident_case_redirect(resident_id)


def edit_budget_session_view(resident_id: int, budget_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    ph = placeholder()

    budget_row = db_fetchone(
        f"""
        SELECT
            id,
            resident_id,
            session_date,
            notes
        FROM resident_budget_sessions
        WHERE id = {ph}
          AND resident_id = {ph}
        LIMIT 1
        """,
        (budget_id, resident_id),
    )

    if not budget_row:
        flash("Budget session not found.", "error")
        return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))

    if request.method == "GET":
        return render_template(
            "case_management/edit_budget_session.html",
            resident=resident,
            budget_row=budget_row,
        )

    session_date = _clean(request.form.get("session_date"))
    notes = _clean(request.form.get("notes"))

    if not session_date:
        flash("Budget session date is required.", "error")
        return redirect(
            url_for(
                "case_management.edit_budget_session",
                resident_id=resident_id,
                budget_id=budget_id,
            )
        )

    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE resident_budget_sessions
        SET
            session_date = {ph},
            notes = {ph},
            updated_at = {ph}
        WHERE id = {ph}
          AND resident_id = {ph}
        """,
        (
            session_date,
            notes,
            now,
            budget_id,
            resident_id,
        ),
    )

    flash("Budget session updated.", "success")
    return _resident_case_redirect(resident_id)
