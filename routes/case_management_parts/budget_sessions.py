from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.budget_sessions_validation import validate_budget_session_form
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    fetch_current_enrollment_id_for_resident,
    normalize_shelter_name,
    parse_money,
    placeholder,
    shelter_equals_sql,
)

_DEFAULT_LINE_ITEMS = (
    ("income", "net_employment", "Net Employment"),
    ("income", "net_ss_ssi_ssdi", "Net SS SSI SSDI"),
    ("income", "child_support", "Child Support"),
    ("income", "cash_gift", "Cash Gift"),
    ("income", "other_income", "Other"),
    ("expense", "rent", "Rent"),
    ("expense", "soap_hygiene", "Soap Hygiene"),
    ("expense", "cigarettes", "Cigarettes"),
    ("expense", "prescription", "Prescription"),
    ("expense", "hospital_doctor", "Hospital Dr."),
    ("expense", "dental", "Dental"),
    ("expense", "cell_phone", "Cell Phone"),
    ("expense", "car_payment", "Car Payment"),
    ("expense", "car_insurance", "Car Insurance"),
    ("expense", "car_maintenance", "Car Maintenance"),
    ("expense", "gasoline", "Gasoline"),
    ("expense", "bus_taxi_lyft_uber", "Bus Taxi Lyft Uber"),
    ("expense", "probation_fees", "Probation Fees"),
    ("expense", "court_fees", "Court Fees"),
    ("expense", "driver_license_surcharge", "Driver License Surcharge"),
    ("expense", "student_loan", "Student Loan"),
    ("expense", "loan_payment", "Loan Payment"),
    ("expense", "child_care", "Child Care"),
    ("expense", "tithe", "Tithe"),
    ("expense", "entertainment", "Entertainment"),
    ("expense", "streamed_media", "Streamed Media"),
    ("expense", "bank_fees", "Bank Fees"),
    ("expense", "savings", "Savings"),
)


def _ensure_budget_session_active_column():
    db_execute("ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT FALSE")


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


def _create_default_line_items(budget_id: int, now: str):
    ph = placeholder()
    existing = db_fetchone(
        f"SELECT id FROM resident_budget_line_items WHERE budget_session_id = {ph} LIMIT 1",
        (budget_id,),
    )
    if existing:
        return

    for idx, (grp, key, label) in enumerate(_DEFAULT_LINE_ITEMS, start=1):
        db_execute(
            f"INSERT INTO resident_budget_line_items (budget_session_id,line_group,line_key,line_label,sort_order,is_resident_visible,is_active,created_at,updated_at) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
            (budget_id, grp, key, label, idx, True, True, now, now),
        )


def _load_line_items(budget_id: int):
    ph = placeholder()
    return db_fetchall(
        f"SELECT * FROM resident_budget_line_items WHERE budget_session_id = {ph} ORDER BY sort_order",
        (budget_id,),
    )


def _update_line_items(budget_id: int, now: str):
    ph = placeholder()
    items = _load_line_items(budget_id)

    for item in items:
        pid = item["id"]
        proj = request.form.get(f"projected_amount_{pid}")
        act = request.form.get(f"actual_amount_{pid}")

        proj_val = parse_money(proj) if proj else None
        act_val = parse_money(act) if act else None

        db_execute(
            f"UPDATE resident_budget_line_items SET projected_amount={ph},actual_amount={ph},updated_at={ph} WHERE id={ph}",
            (proj_val, act_val, now, pid),
        )


def budget_sessions_view(resident_id: int):
    init_db()
    if not case_manager_allowed():
        return _resident_case_redirect(resident_id)

    _ensure_budget_session_active_column()

    resident = _resident_context(resident_id)
    if not resident:
        return redirect(url_for("case_management.index"))

    rows = db_fetchall(
        "SELECT * FROM resident_budget_sessions WHERE resident_id=? ORDER BY COALESCE(is_active,0) DESC, id DESC",
        (resident_id,),
    )

    return render_template("case_management/budget_sessions.html", resident=resident, budget_rows=rows)


def add_budget_session_view(resident_id: int):
    init_db()
    resident = _resident_context(resident_id)
    data, errors = validate_budget_session_form(request.form)

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))

    duplicate = db_fetchone(
        "SELECT id FROM resident_budget_sessions WHERE resident_id = ? AND enrollment_id = ? AND budget_month = ? LIMIT 1",
        (resident_id, resident.get("enrollment_id"), data["budget_month"]),
    )
    if duplicate:
        flash("A budget for that month already exists for this resident.", "error")
        return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))

    now = utcnow_iso()
    ph = placeholder()

    with db_transaction():
        _ensure_budget_session_active_column()

        db_execute("UPDATE resident_budget_sessions SET is_active = FALSE WHERE resident_id = ?", (resident_id,))

        db_execute(
            f"INSERT INTO resident_budget_sessions (resident_id,enrollment_id,session_date,budget_month,staff_user_id,notes,created_at,updated_at,is_active) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},1)",
            (resident_id, resident.get("enrollment_id"), data["session_date"], data["budget_month"], session.get("staff_user_id"), data["notes"], now, now),
        )

        row = db_fetchone("SELECT id FROM resident_budget_sessions WHERE resident_id=? ORDER BY id DESC LIMIT 1", (resident_id,))
        bid = row["id"]
        _create_default_line_items(bid, now)

    return redirect(url_for("case_management.edit_budget_session", resident_id=resident_id, budget_id=bid))


def edit_budget_session_view(resident_id: int, budget_id: int):
    init_db()
    resident = _resident_context(resident_id)

    row = db_fetchone("SELECT * FROM resident_budget_sessions WHERE id=?", (budget_id,))
    now = utcnow_iso()

    _create_default_line_items(budget_id, now)
    items = _load_line_items(budget_id)

    if request.method == "GET":
        return render_template("case_management/edit_budget_session.html", resident=resident, budget_row=row, budget_line_items=items)

    _update_line_items(budget_id, now)

    flash("Budget updated", "success")
    return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))
