from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.budget_sessions_validation import validate_budget_session_form
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    fetch_current_enrollment_id_for_resident,
    normalize_shelter_name,
    placeholder,
    shelter_equals_sql,
)


def _resident_case_redirect(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _resident_context(resident_id: int):
    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT id, first_name, last_name, shelter
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
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
        SELECT id, session_date, budget_month, projected_total_income, actual_total_income
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

    data, errors = validate_budget_session_form(request.form)

    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))

    now = utcnow_iso()
    ph = placeholder()

    db_execute(
        f"""
        INSERT INTO resident_budget_sessions (
            resident_id,
            enrollment_id,
            session_date,
            budget_month,
            projected_total_income,
            actual_total_income,
            projected_total_expenses,
            actual_total_expenses,
            projected_remaining_income,
            actual_remaining_income,
            last_month_savings,
            this_month_savings,
            house_contribution_amount,
            personal_amount,
            amount_left_for_abba,
            staff_user_id,
            notes,
            created_at,
            updated_at
        )
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
        """,
        (
            resident_id,
            resident.get("enrollment_id"),
            data["session_date"],
            data["budget_month"],
            data["projected_total_income"],
            data["actual_total_income"],
            data["projected_total_expenses"],
            data["actual_total_expenses"],
            data["projected_remaining_income"],
            data["actual_remaining_income"],
            data["last_month_savings"],
            data["this_month_savings"],
            data["house_contribution_amount"],
            data["personal_amount"],
            data["amount_left_for_abba"],
            session.get("staff_user_id"),
            data["notes"],
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
        SELECT *
        FROM resident_budget_sessions
        WHERE id = {ph} AND resident_id = {ph}
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

    data, errors = validate_budget_session_form(request.form)

    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("case_management.edit_budget_session", resident_id=resident_id, budget_id=budget_id))

    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE resident_budget_sessions
        SET
            session_date = {ph},
            budget_month = {ph},
            projected_total_income = {ph},
            actual_total_income = {ph},
            projected_total_expenses = {ph},
            actual_total_expenses = {ph},
            projected_remaining_income = {ph},
            actual_remaining_income = {ph},
            last_month_savings = {ph},
            this_month_savings = {ph},
            house_contribution_amount = {ph},
            personal_amount = {ph},
            amount_left_for_abba = {ph},
            notes = {ph},
            updated_at = {ph}
        WHERE id = {ph} AND resident_id = {ph}
        """,
        (
            data["session_date"],
            data["budget_month"],
            data["projected_total_income"],
            data["actual_total_income"],
            data["projected_total_expenses"],
            data["actual_total_expenses"],
            data["projected_remaining_income"],
            data["actual_remaining_income"],
            data["last_month_savings"],
            data["this_month_savings"],
            data["house_contribution_amount"],
            data["personal_amount"],
            data["amount_left_for_abba"],
            data["notes"],
            now,
            budget_id,
            resident_id,
        ),
    )

    flash("Budget session updated.", "success")
    return _resident_case_redirect(resident_id)
