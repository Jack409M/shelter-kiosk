from __future__ import annotations

from datetime import datetime

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.budget_sessions_validation import validate_budget_session_form
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    clean,
    fetch_current_enrollment_id_for_resident,
    normalize_shelter_name,
    parse_money,
    placeholder,
    shelter_equals_sql,
)
from routes.case_management_parts.intake_income_support import load_intake_income_support

_DEFAULT_LINE_ITEMS = (
    ("income", "net_employment", "Net Employment"),
    ("income", "net_ss_ssi_ssdi", "SS SSI SSDI Survivor Benefits"),
    ("income", "tanf", "TANF"),
    ("income", "child_support", "Child Support"),
    ("income", "alimony", "Alimony"),
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


def _ensure_budget_session_active_column() -> None:
    db_execute(
        "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT FALSE"
    )



def _resident_case_redirect(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))



def _parse_budget_month(month_text: str | None) -> datetime | None:
    normalized = str(month_text or "").strip()
    if not normalized:
        return None
    try:
        return datetime.strptime(normalized, "%Y-%m")
    except ValueError:
        return None



def _format_budget_month(month_text: str | None) -> str:
    parsed = _parse_budget_month(month_text)
    if parsed is None:
        return "Missing Month"
    return parsed.strftime("%B %Y")



def _next_month_text(month_text: str | None) -> str:
    parsed = _parse_budget_month(month_text)
    if parsed is None:
        current_month = datetime.strptime(utcnow_iso()[:7], "%Y-%m")
        return current_month.strftime("%Y-%m")

    year = parsed.year + (1 if parsed.month == 12 else 0)
    month = 1 if parsed.month == 12 else parsed.month + 1
    return f"{year:04d}-{month:02d}"



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



def _load_budget_rows_for_resident(resident_id: int) -> list[dict]:
    rows = db_fetchall(
        """
        SELECT *
        FROM resident_budget_sessions
        WHERE resident_id = ?
        ORDER BY
            CASE WHEN budget_month IS NULL THEN 1 ELSE 0 END,
            budget_month DESC,
            id DESC
        """,
        (resident_id,),
    )
    return [dict(row) for row in (rows or [])]



def _decorate_budget_rows(rows: list[dict]) -> tuple[list[dict], dict | None, list[dict]]:
    current_row_id = None

    for row in rows:
        if bool(row.get("is_active")):
            current_row_id = row["id"]
            break

    if current_row_id is None and rows:
        current_row_id = rows[0]["id"]

    all_rows: list[dict] = []
    current_row: dict | None = None
    past_rows: list[dict] = []

    for row in rows:
        item = dict(row)
        item["budget_month_label"] = _format_budget_month(item.get("budget_month"))
        item["is_current"] = item["id"] == current_row_id
        all_rows.append(item)
        if item["is_current"] and current_row is None:
            current_row = item
        else:
            past_rows.append(item)

    return all_rows, current_row, past_rows



def _build_budget_page_context(resident_id: int) -> dict:
    raw_rows = _load_budget_rows_for_resident(resident_id)
    all_rows, current_row, past_rows = _decorate_budget_rows(raw_rows)

    suggested_session_date = utcnow_iso()[:10]
    if current_row:
        suggested_budget_month = _next_month_text(current_row.get("budget_month"))
        suggested_action_label = f"Create {_format_budget_month(suggested_budget_month)} Budget"
        suggested_help_text = (
            "This creates the next month, copies last month planned expenses, reloads income from the system, and clears actual amounts."
        )
    else:
        suggested_budget_month = utcnow_iso()[:7]
        suggested_action_label = f"Create {_format_budget_month(suggested_budget_month)} Budget"
        suggested_help_text = (
            "Start the first monthly budget for this resident. Future months will copy forward planned expenses automatically."
        )

    return {
        "all_budget_rows": all_rows,
        "current_budget": current_row,
        "past_budget_rows": past_rows,
        "suggested_budget_month": suggested_budget_month,
        "suggested_budget_month_label": _format_budget_month(suggested_budget_month),
        "suggested_session_date": suggested_session_date,
        "suggested_action_label": suggested_action_label,
        "suggested_help_text": suggested_help_text,
    }



def _create_default_line_items(budget_id: int, now: str) -> None:
    ph = placeholder()
    existing = db_fetchone(
        f"SELECT id FROM resident_budget_line_items WHERE budget_session_id = {ph} LIMIT 1",
        (budget_id,),
    )
    if existing:
        return

    for idx, (group_name, line_key, line_label) in enumerate(_DEFAULT_LINE_ITEMS, start=1):
        db_execute(
            f"""
            INSERT INTO resident_budget_line_items
            (
                budget_session_id,
                line_group,
                line_key,
                line_label,
                sort_order,
                is_resident_visible,
                is_active,
                created_at,
                updated_at
            )
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
            """,
            (budget_id, group_name, line_key, line_label, idx, True, True, now, now),
        )



def _copy_forward_previous_budget(
    budget_id: int,
    resident_id: int,
    enrollment_id: int | None,
    budget_month: str | None,
    now: str,
) -> None:
    if not enrollment_id or not budget_month:
        return

    previous_budget = db_fetchone(
        """
        SELECT id
        FROM resident_budget_sessions
        WHERE resident_id = ?
          AND enrollment_id = ?
          AND id <> ?
          AND budget_month IS NOT NULL
          AND budget_month < ?
        ORDER BY budget_month DESC, id DESC
        LIMIT 1
        """,
        (resident_id, enrollment_id, budget_id, budget_month),
    )
    if not previous_budget:
        return

    previous_items = db_fetchall(
        """
        SELECT line_key, line_group, projected_amount
        FROM resident_budget_line_items
        WHERE budget_session_id = ?
          AND COALESCE(is_active, TRUE) = TRUE
        """,
        (previous_budget["id"],),
    )
    if not previous_items:
        return

    previous_expense_by_key = {
        str(item.get("line_key") or "").strip(): item
        for item in previous_items
        if str(item.get("line_group") or "").strip().lower() == "expense"
        and str(item.get("line_key") or "").strip()
    }

    current_items = db_fetchall(
        """
        SELECT id, line_group, line_key
        FROM resident_budget_line_items
        WHERE budget_session_id = ?
          AND COALESCE(is_active, TRUE) = TRUE
        """,
        (budget_id,),
    )

    for item in current_items or []:
        if str(item.get("line_group") or "").strip().lower() != "expense":
            continue

        line_key = str(item.get("line_key") or "").strip()
        previous = previous_expense_by_key.get(line_key)
        if not previous:
            continue

        previous_projected = previous.get("projected_amount")
        projected_amount = (
            round(float(previous_projected), 2)
            if previous_projected not in (None, "")
            else None
        )
        db_execute(
            """
            UPDATE resident_budget_line_items
            SET projected_amount = ?, actual_amount = NULL, updated_at = ?
            WHERE id = ?
            """,
            (projected_amount, now, item["id"]),
        )



def _prefill_income_from_source(budget_id: int, enrollment_id: int | None, now: str) -> None:
    income = load_intake_income_support(enrollment_id) or {}

    employment_total = (
        float(income.get("employment_income_1") or 0)
        + float(income.get("employment_income_2") or 0)
        + float(income.get("employment_income_3") or 0)
    )
    ssi_survivor_total = float(income.get("ssi_ssdi_income") or 0) + float(
        income.get("survivor_benefit_total") or 0
    )
    tanf_total = float(income.get("tanf_income") or 0)
    child_support_total = float(
        income.get("child_support_total") or income.get("child_support_income") or 0
    )
    alimony_total = float(income.get("alimony_income") or 0)
    other_total = float(income.get("other_income") or 0)

    mapping = {
        "net_employment": round(employment_total, 2),
        "net_ss_ssi_ssdi": round(ssi_survivor_total, 2),
        "tanf": round(tanf_total, 2),
        "child_support": round(child_support_total, 2),
        "alimony": round(alimony_total, 2),
        "other_income": round(other_total, 2),
    }

    rows = db_fetchall(
        """
        SELECT id, line_key
        FROM resident_budget_line_items
        WHERE budget_session_id = ?
          AND line_group = 'income'
        ORDER BY sort_order, id
        """,
        (budget_id,),
    )

    for row in rows or []:
        key = str(row.get("line_key") or "").strip()
        projected_amount = mapping.get(key)
        db_execute(
            """
            UPDATE resident_budget_line_items
            SET projected_amount = ?, actual_amount = NULL, updated_at = ?
            WHERE id = ?
            """,
            (projected_amount, now, row["id"]),
        )



def _load_line_items(budget_id: int) -> list[dict]:
    ph = placeholder()
    rows = db_fetchall(
        f"""
        SELECT *
        FROM resident_budget_line_items
        WHERE budget_session_id = {ph}
        ORDER BY sort_order, id
        """,
        (budget_id,),
    )
    return [dict(row) for row in (rows or [])]



def _coerce_money(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0



def _split_expense_items(expense_items: list[dict]) -> tuple[list[dict], list[dict]]:
    midpoint = (len(expense_items) + 1) // 2
    return expense_items[:midpoint], expense_items[midpoint:]



def _build_edit_context(resident_id: int, budget_row: dict, budget_line_items: list[dict]) -> dict:
    decorated_budget_row = dict(budget_row)
    decorated_budget_row["budget_month_label"] = _format_budget_month(
        decorated_budget_row.get("budget_month")
    )

    income_items: list[dict] = []
    expense_items: list[dict] = []

    for item in budget_line_items:
        entry = dict(item)
        entry["projected_amount"] = _coerce_money(entry.get("projected_amount"))
        entry["actual_amount"] = _coerce_money(entry.get("actual_amount"))
        entry["difference_amount"] = round(entry["actual_amount"] - entry["projected_amount"], 2)
        if entry["difference_amount"] > 0:
            entry["difference_text"] = f"+${entry['difference_amount']:.2f}"
        elif entry["difference_amount"] < 0:
            entry["difference_text"] = f"-${abs(entry['difference_amount']):.2f}"
        else:
            entry["difference_text"] = "$0.00"

        if str(entry.get("line_group") or "").strip().lower() == "income":
            income_items.append(entry)
        else:
            expense_items.append(entry)

    total_income = round(sum(item["projected_amount"] for item in income_items), 2)
    total_expenses = round(sum(item["projected_amount"] for item in expense_items), 2)
    balance = round(total_income - total_expenses, 2)
    expense_left_items, expense_right_items = _split_expense_items(expense_items)

    budget_month = str(decorated_budget_row.get("budget_month") or "").strip()
    budget_month_start = f"{budget_month}-01" if budget_month else ""

    page_context = _build_budget_page_context(resident_id)
    page_context.update(
        {
            "budget_row": decorated_budget_row,
            "budget_line_items": budget_line_items,
            "income_items": income_items,
            "expense_left_items": expense_left_items,
            "expense_right_items": expense_right_items,
            "transaction_expense_items": expense_items,
            "recent_transactions": [],
            "can_edit_expense_budget": True,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "balance": balance,
            "budget_month_start": budget_month_start,
        }
    )
    return page_context



def _update_line_items(budget_id: int, now: str) -> None:
    ph = placeholder()
    items = _load_line_items(budget_id)

    for item in items:
        item_id = item["id"]
        projected_amount = parse_money(request.form.get(f"projected_amount_{item_id}"))
        actual_amount = parse_money(request.form.get(f"actual_amount_{item_id}"))
        db_execute(
            f"""
            UPDATE resident_budget_line_items
            SET projected_amount = {ph},
                actual_amount = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (projected_amount, actual_amount, now, item_id),
        )



def budget_sessions_view(resident_id: int):
    init_db()
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    _ensure_budget_session_active_column()
    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    return render_template(
        "case_management/budget_sessions.html",
        resident=resident,
        **_build_budget_page_context(resident_id),
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
        for error_text in errors:
            flash(error_text, "error")
        return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))

    duplicate = db_fetchone(
        """
        SELECT id
        FROM resident_budget_sessions
        WHERE resident_id = ?
          AND enrollment_id = ?
          AND budget_month = ?
        LIMIT 1
        """,
        (resident_id, resident.get("enrollment_id"), data.get("budget_month")),
    )
    if duplicate:
        flash("A budget for that month already exists for this resident.", "error")
        return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))

    now = utcnow_iso()
    ph = placeholder()

    with db_transaction():
        _ensure_budget_session_active_column()
        db_execute(
            "UPDATE resident_budget_sessions SET is_active = FALSE WHERE resident_id = ?",
            (resident_id,),
        )
        db_execute(
            f"""
            INSERT INTO resident_budget_sessions
            (
                resident_id,
                enrollment_id,
                session_date,
                budget_month,
                staff_user_id,
                notes,
                created_at,
                updated_at,
                is_active
            )
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},TRUE)
            """,
            (
                resident_id,
                resident.get("enrollment_id"),
                data.get("session_date"),
                data.get("budget_month"),
                session.get("staff_user_id"),
                data.get("notes"),
                now,
                now,
            ),
        )
        row = db_fetchone(
            """
            SELECT id
            FROM resident_budget_sessions
            WHERE resident_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (resident_id,),
        )
        budget_id = row["id"]
        _create_default_line_items(budget_id, now)
        _copy_forward_previous_budget(
            budget_id,
            resident_id,
            resident.get("enrollment_id"),
            data.get("budget_month"),
            now,
        )
        _prefill_income_from_source(budget_id, resident.get("enrollment_id"), now)

    flash(f"{_format_budget_month(data.get('budget_month'))} budget created.", "success")
    return redirect(
        url_for(
            "case_management.edit_budget_session",
            resident_id=resident_id,
            budget_id=budget_id,
        )
    )



def edit_budget_session_view(resident_id: int, budget_id: int):
    init_db()
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    row = db_fetchone(
        """
        SELECT *
        FROM resident_budget_sessions
        WHERE id = ?
          AND resident_id = ?
        LIMIT 1
        """,
        (budget_id, resident_id),
    )
    if not row:
        flash("Budget month not found for this resident.", "error")
        return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))

    now = utcnow_iso()
    _create_default_line_items(budget_id, now)

    if request.method == "POST":
        _update_line_items(budget_id, now)
        db_execute(
            """
            UPDATE resident_budget_sessions
            SET notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (clean(request.form.get("notes")), now, budget_id),
        )
        flash("Budget updated.", "success")
        return redirect(
            url_for(
                "case_management.edit_budget_session",
                resident_id=resident_id,
                budget_id=budget_id,
            )
        )

    budget_line_items = _load_line_items(budget_id)
    return render_template(
        "case_management/edit_budget_session.html",
        resident=resident,
        **_build_edit_context(resident_id, dict(row), budget_line_items),
    )



def delete_budget_session_view(resident_id: int, budget_id: int):
    init_db()
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    resident = _resident_context(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    row = db_fetchone(
        """
        SELECT id, is_active
        FROM resident_budget_sessions
        WHERE id = ?
          AND resident_id = ?
        LIMIT 1
        """,
        (budget_id, resident_id),
    )
    if not row:
        flash("Budget month not found for this resident.", "error")
        return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))

    with db_transaction():
        db_execute(
            "DELETE FROM resident_budget_line_items WHERE budget_session_id = ?",
            (budget_id,),
        )
        db_execute(
            "DELETE FROM resident_budget_sessions WHERE id = ? AND resident_id = ?",
            (budget_id, resident_id),
        )
        if bool(row.get("is_active")):
            replacement = db_fetchone(
                """
                SELECT id
                FROM resident_budget_sessions
                WHERE resident_id = ?
                ORDER BY
                    CASE WHEN budget_month IS NULL THEN 1 ELSE 0 END,
                    budget_month DESC,
                    id DESC
                LIMIT 1
                """,
                (resident_id,),
            )
            if replacement:
                db_execute(
                    "UPDATE resident_budget_sessions SET is_active = TRUE WHERE id = ?",
                    (replacement["id"],),
                )

    flash("Budget deleted.", "success")
    return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))
