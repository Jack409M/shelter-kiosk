from __future__ import annotations

from datetime import datetime, timedelta

from flask import flash, g, redirect, render_template, request, session, url_for

from core.budget_registry import is_budget_expense_key, iter_budget_line_item_definitions
from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.budget_sessions_validation import (
    validate_budget_session_form,
)
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


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _current_budget_month_text() -> str:
    return utcnow_iso()[:7]


def _safe_positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    return parsed if parsed > 0 else None


def _ensure_budget_session_active_column() -> None:
    if g.get("db_kind") == "pg":
        db_execute(
            "ALTER TABLE resident_budget_sessions "
            "ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT FALSE"
        )
        return

    columns = db_fetchall("PRAGMA table_info(resident_budget_sessions)")
    if any(
        str(column.get("name") or "").strip().lower() == "is_active"
        for column in columns or []
    ):
        return

    db_execute("ALTER TABLE resident_budget_sessions ADD COLUMN is_active INTEGER DEFAULT 0")


def _resident_case_redirect(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _resident_context(resident_id: int) -> dict | None:
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

    resident_dict = dict(resident)
    resident_dict["enrollment_id"] = fetch_current_enrollment_id_for_resident(resident_id)
    return resident_dict


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
        current_month = datetime.strptime(_current_budget_month_text(), "%Y-%m")
        return current_month.strftime("%Y-%m")

    year = parsed.year + (1 if parsed.month == 12 else 0)
    month = 1 if parsed.month == 12 else parsed.month + 1
    return f"{year:04d}-{month:02d}"


def _is_future_budget_month(month_text: str | None) -> bool:
    normalized = str(month_text or "").strip()
    if not normalized:
        return False
    return normalized > _current_budget_month_text()


def _determine_active_budget_session_id(rows: list[dict]) -> int | None:
    if not rows:
        return None

    current_month = _current_budget_month_text()

    exact_current = [
        row
        for row in rows
        if str(row.get("budget_month") or "").strip() == current_month
    ]
    if exact_current:
        exact_current.sort(
            key=lambda row: (
                str(row.get("budget_month") or ""),
                int(row.get("id") or 0),
            ),
            reverse=True,
        )
        return int(exact_current[0]["id"])

    past_or_current = [
        row
        for row in rows
        if str(row.get("budget_month") or "").strip()
        and str(row.get("budget_month") or "").strip() <= current_month
    ]
    if past_or_current:
        past_or_current.sort(
            key=lambda row: (
                str(row.get("budget_month") or ""),
                int(row.get("id") or 0),
            ),
            reverse=True,
        )
        return int(past_or_current[0]["id"])

    future_rows = [
        row
        for row in rows
        if str(row.get("budget_month") or "").strip()
    ]
    if future_rows:
        future_rows.sort(
            key=lambda row: (
                str(row.get("budget_month") or ""),
                int(row.get("id") or 0),
            )
        )
        return int(future_rows[0]["id"])

    fallback_rows = sorted(
        rows,
        key=lambda row: int(row.get("id") or 0),
        reverse=True,
    )
    return int(fallback_rows[0]["id"])


def _set_active_budget_session_for_resident(
    resident_id: int, budget_id: int | None
) -> None:
    db_execute(
        _sql(
            "UPDATE resident_budget_sessions SET is_active = FALSE WHERE resident_id = %s",
            "UPDATE resident_budget_sessions SET is_active = 0 WHERE resident_id = ?",
        ),
        (resident_id,),
    )
    if budget_id is None:
        return

    db_execute(
        _sql(
            "UPDATE resident_budget_sessions SET is_active = TRUE WHERE id = %s",
            "UPDATE resident_budget_sessions SET is_active = 1 WHERE id = ?",
        ),
        (budget_id,),
    )


def _refresh_active_budget_session_for_resident(resident_id: int) -> int | None:
    rows = _load_budget_rows_for_resident(resident_id)
    active_budget_id = _determine_active_budget_session_id(rows)
    _set_active_budget_session_for_resident(resident_id, active_budget_id)
    return active_budget_id


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
        current_row_id = _determine_active_budget_session_id(rows)

    all_rows: list[dict] = []
    current_row: dict | None = None
    past_rows: list[dict] = []

    for row in rows:
        item = dict(row)
        item["budget_month_label"] = _format_budget_month(item.get("budget_month"))
        item["is_current"] = item["id"] == current_row_id
        item["is_future_budget"] = _is_future_budget_month(item.get("budget_month"))
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
            "This creates the next month, copies last month planned expenses, "
            "reloads income from the system, and leaves resident spending tied "
            "to the correct active month."
        )
    else:
        suggested_budget_month = _current_budget_month_text()
        suggested_action_label = f"Create {_format_budget_month(suggested_budget_month)} Budget"
        suggested_help_text = (
            "Start the first monthly budget for this resident. Future months "
            "will copy forward planned expenses automatically."
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
    existing_rows = db_fetchall(
        f"SELECT id, line_key FROM resident_budget_line_items WHERE budget_session_id = {ph}",
        (budget_id,),
    )
    existing_by_key = {
        str(row.get("line_key") or "").strip(): dict(row)
        for row in (existing_rows or [])
        if str(row.get("line_key") or "").strip()
    }

    for idx, item in enumerate(iter_budget_line_item_definitions(), start=1):
        line_key = str(item["line_key"])
        existing = existing_by_key.get(line_key)

        if existing:
            db_execute(
                """
                UPDATE resident_budget_line_items
                SET line_group = ?,
                    line_label = ?,
                    sort_order = ?,
                    is_resident_visible = ?,
                    is_active = TRUE,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    item["line_group"],
                    item["line_label"],
                    idx,
                    item.get("is_resident_visible", True),
                    now,
                    existing["id"],
                ),
            )
            continue

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
            (
                budget_id,
                item["line_group"],
                item["line_key"],
                item["line_label"],
                idx,
                item.get("is_resident_visible", True),
                True,
                now,
                now,
            ),
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

    previous_expense_by_key = {
        str(item.get("line_key") or "").strip(): item
        for item in (previous_items or [])
        if str(item.get("line_group") or "").strip().lower() == "expense"
        and str(item.get("line_key") or "").strip()
    }

    current_items = db_fetchall(
        """
        SELECT id, line_key
        FROM resident_budget_line_items
        WHERE budget_session_id = ?
          AND COALESCE(is_active, TRUE) = TRUE
        """,
        (budget_id,),
    )

    for item in current_items or []:
        line_key = str(item.get("line_key") or "").strip()
        if not is_budget_expense_key(line_key):
            continue

        previous = previous_expense_by_key.get(line_key)
        if not previous:
            continue

        projected = previous.get("projected_amount")
        projected_amount = (
            round(float(projected), 2) if projected not in (None, "") else None
        )

        db_execute(
            """
            UPDATE resident_budget_line_items
            SET projected_amount = ?, updated_at = ?
            WHERE id = ?
            """,
            (projected_amount, now, item["id"]),
        )


def _prefill_income_from_source(
    budget_id: int, enrollment_id: int | None, now: str
) -> None:
    income = load_intake_income_support(enrollment_id) or {}

    mapping = {
        "net_employment": float(income.get("employment_income_1") or 0)
        + float(income.get("employment_income_2") or 0)
        + float(income.get("employment_income_3") or 0),
        "net_ss_ssi_ssdi": float(income.get("ssi_ssdi_income") or 0)
        + float(income.get("survivor_benefit_total") or 0),
        "tanf": float(income.get("tanf_income") or 0),
        "child_support": float(
            income.get("child_support_total")
            or income.get("child_support_income")
            or 0
        ),
        "alimony": float(income.get("alimony_income") or 0),
        "other_income": float(income.get("other_income") or 0),
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
            SET projected_amount = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                round(projected_amount, 2) if projected_amount not in (None, 0) else None,
                now,
                row["id"],
            ),
        )


def _format_difference_text(amount: float) -> str:
    rounded = round(float(amount or 0), 2)
    if rounded > 0:
        return f"${rounded:,.2f} Over"
    if rounded < 0:
        return f"${abs(rounded):,.2f} Under"
    return "$0.00"


def _difference_class(amount: float) -> str:
    rounded = round(float(amount or 0), 2)
    if rounded > 0:
        return "over"
    if rounded < 0:
        return "under"
    return "even"


def _parse_transaction_date(date_text: str | None) -> datetime | None:
    value = str(date_text or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def _budget_month_bounds(budget_month: str | None) -> tuple[str | None, str | None]:
    parsed = _parse_budget_month(budget_month)
    if parsed is None:
        return None, None

    start_of_month = parsed.replace(day=1)
    if start_of_month.month == 12:
        next_month = datetime(start_of_month.year + 1, 1, 1)
    else:
        next_month = datetime(start_of_month.year, start_of_month.month + 1, 1)

    month_end = next_month - timedelta(days=1)
    return start_of_month.strftime("%Y-%m-%d"), month_end.strftime("%Y-%m-%d")


def _load_line_items(budget_id: int) -> list[dict]:
    rows = db_fetchall(
        _sql(
            """
            SELECT
                li.*,
                COALESCE(
                    SUM(
                        CASE
                            WHEN COALESCE(t.is_deleted, FALSE) = FALSE THEN t.amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS txn_total
            FROM resident_budget_line_items li
            LEFT JOIN resident_budget_transactions t ON t.line_item_id = li.id
            WHERE li.budget_session_id = %s
              AND COALESCE(li.is_active, TRUE) = TRUE
            GROUP BY li.id
            ORDER BY li.sort_order, li.id
            """,
            """
            SELECT
                li.*,
                COALESCE(
                    SUM(
                        CASE
                            WHEN COALESCE(t.is_deleted, 0) = 0 THEN t.amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS txn_total
            FROM resident_budget_line_items li
            LEFT JOIN resident_budget_transactions t ON t.line_item_id = li.id
            WHERE li.budget_session_id = ?
              AND COALESCE(li.is_active, 1) = 1
            GROUP BY li.id
            ORDER BY li.sort_order, li.id
            """,
        ),
        (budget_id,),
    )

    items: list[dict] = []
    for row in rows or []:
        item = dict(row)
        projected_amount = float(item.get("projected_amount") or 0)

        if is_budget_expense_key(item.get("line_key")):
            total_amount = float(item.get("txn_total") or 0)
            item["actual_amount"] = round(total_amount, 2)
            item["actual_editable"] = False
        else:
            total_amount = float(item.get("actual_amount") or 0)
            item["actual_editable"] = True

        difference_amount = round(total_amount - projected_amount, 2)
        item["projected_amount"] = (
            round(projected_amount, 2) if projected_amount else None
        )
        item["difference_amount"] = difference_amount
        item["difference_text"] = _format_difference_text(difference_amount)
        item["difference_class"] = _difference_class(difference_amount)
        items.append(item)

    return items


def _load_budget_line_item_lookup(budget_id: int) -> dict[int, dict]:
    rows = db_fetchall(
        """
        SELECT id, budget_session_id, line_group, line_key, line_label
        FROM resident_budget_line_items
        WHERE budget_session_id = ?
          AND COALESCE(is_active, TRUE) = TRUE
        ORDER BY sort_order, id
        """,
        (budget_id,),
    )
    return {int(row["id"]): dict(row) for row in rows or []}


def _split_expense_items(expense_items: list[dict]) -> tuple[list[dict], list[dict]]:
    midpoint = (len(expense_items) + 1) // 2
    return expense_items[:midpoint], expense_items[midpoint:]


def _load_recent_budget_transactions(budget_id: int, limit: int = 24) -> list[dict]:
    rows = db_fetchall(
        _sql(
            """
            SELECT
                t.id,
                t.line_item_id,
                t.transaction_date,
                t.amount,
                t.merchant_or_note,
                li.line_label,
                t.edited_at,
                t.entered_by_role,
                t.edited_by_role
            FROM resident_budget_transactions t
            LEFT JOIN resident_budget_line_items li ON li.id = t.line_item_id
            WHERE t.budget_session_id = %s
              AND COALESCE(t.is_deleted, FALSE) = FALSE
            ORDER BY t.transaction_date DESC, t.id DESC
            LIMIT %s
            """,
            """
            SELECT
                t.id,
                t.line_item_id,
                t.transaction_date,
                t.amount,
                t.merchant_or_note,
                li.line_label,
                t.edited_at,
                t.entered_by_role,
                t.edited_by_role
            FROM resident_budget_transactions t
            LEFT JOIN resident_budget_line_items li ON li.id = t.line_item_id
            WHERE t.budget_session_id = ?
              AND COALESCE(t.is_deleted, 0) = 0
            ORDER BY t.transaction_date DESC, t.id DESC
            LIMIT ?
            """,
        ),
        (budget_id, limit),
    )
    return [dict(row) for row in rows or []]


def _build_budget_editor_context(budget_id: int, budget_month: str | None) -> dict:
    items = _load_line_items(budget_id)
    income_items = [
        item
        for item in items
        if str(item.get("line_group") or "").strip().lower() == "income"
    ]
    expense_items = [
        item
        for item in items
        if str(item.get("line_group") or "").strip().lower() == "expense"
    ]
    expense_left_items, expense_right_items = _split_expense_items(expense_items)

    total_budgeted_income = round(
        sum(float(item.get("projected_amount") or 0) for item in income_items),
        2,
    )
    total_budgeted_expenses = round(
        sum(float(item.get("projected_amount") or 0) for item in expense_items),
        2,
    )
    total_actual_expenses = round(
        sum(float(item.get("actual_amount") or 0) for item in expense_items),
        2,
    )
    total_remaining = round(total_budgeted_income - total_actual_expenses, 2)

    recent_transactions = _load_recent_budget_transactions(budget_id)
    line_item_lookup = _load_budget_line_item_lookup(budget_id)
    transaction_expense_items = [
        item
        for item in line_item_lookup.values()
        if str(item.get("line_group") or "").strip().lower() == "expense"
    ]
    month_start, month_end = _budget_month_bounds(budget_month)

    return {
        "budget_line_items": items,
        "income_items": income_items,
        "expense_left_items": expense_left_items,
        "expense_right_items": expense_right_items,
        "recent_transactions": recent_transactions,
        "transaction_expense_items": transaction_expense_items,
        "budget_month_start": month_start,
        "budget_month_end": month_end,
        "can_edit_expense_budget": _is_future_budget_month(budget_month),
        "total_income": total_budgeted_income,
        "total_expenses": total_actual_expenses,
        "balance": total_remaining,
        "total_budgeted_income": total_budgeted_income,
        "total_budgeted_expenses": total_budgeted_expenses,
        "total_actual_expenses": total_actual_expenses,
        "total_remaining": total_remaining,
    }


def _validate_transaction_inputs(
    *,
    budget_row: dict,
    line_item_lookup: dict[int, dict],
    transaction_date: str,
    line_item_id: int | None,
    amount_raw: str | None,
) -> tuple[list[str], float | None]:
    errors: list[str] = []

    parsed_date = _parse_transaction_date(transaction_date)
    if parsed_date is None:
        errors.append("Transaction date must be a valid date.")

    amount = parse_money(amount_raw)
    if amount is None or amount <= 0:
        errors.append("Amount must be greater than zero.")

    selected_item = line_item_lookup.get(line_item_id or 0)
    if not selected_item:
        errors.append("Please select a valid expense category.")
    elif str(selected_item.get("line_group") or "").strip().lower() != "expense":
        errors.append("Transactions can only be logged to an expense category.")
    elif int(selected_item.get("budget_session_id") or 0) != int(budget_row.get("id") or 0):
        errors.append("Expense category does not belong to this budget month.")

    month_start, month_end = _budget_month_bounds(budget_row.get("budget_month"))
    if (
        parsed_date is not None
        and month_start
        and month_end
        and not (month_start <= transaction_date <= month_end)
    ):
        errors.append(
            "Transaction date must stay inside this budget month. "
            f"Allowed range: {month_start} to {month_end}."
        )

    return errors, round(amount, 2) if amount is not None else None


def _load_staff_transaction(transaction_id: int, budget_id: int, resident_id: int):
    return db_fetchone(
        _sql(
            """
            SELECT id, budget_session_id, resident_id, line_item_id, transaction_date, amount, merchant_or_note
            FROM resident_budget_transactions
            WHERE id = %s
              AND budget_session_id = %s
              AND resident_id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            LIMIT 1
            """,
            """
            SELECT id, budget_session_id, resident_id, line_item_id, transaction_date, amount, merchant_or_note
            FROM resident_budget_transactions
            WHERE id = ?
              AND budget_session_id = ?
              AND resident_id = ?
              AND COALESCE(is_deleted, 0) = 0
            LIMIT 1
            """,
        ),
        (transaction_id, budget_id, resident_id),
    )


def _update_future_budget_line_items_only(budget_id: int, now: str) -> None:
    items = _load_line_items(budget_id)

    for item in items:
        item_id = item["id"]
        line_group = str(item.get("line_group") or "").strip().lower()

        projected_raw = request.form.get(f"projected_amount_{item_id}")
        projected_value = parse_money(projected_raw) if projected_raw else None

        if line_group == "income":
            actual_raw = request.form.get(f"actual_amount_{item_id}")
            actual_value = parse_money(actual_raw) if actual_raw else None
            db_execute(
                """
                UPDATE resident_budget_line_items
                SET projected_amount = ?, actual_amount = ?, updated_at = ?
                WHERE id = ?
                """,
                (projected_value, actual_value, now, item_id),
            )
            continue

        db_execute(
            """
            UPDATE resident_budget_line_items
            SET projected_amount = ?, updated_at = ?
            WHERE id = ?
            """,
            (projected_value, now, item_id),
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

    _refresh_active_budget_session_for_resident(resident_id)
    page_context = _build_budget_page_context(resident_id)

    return render_template(
        "case_management/budget_sessions.html",
        resident=resident,
        **page_context,
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
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
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
                False if g.get("db_kind") == "pg" else 0,
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
            budget_id=budget_id,
            resident_id=resident_id,
            enrollment_id=resident.get("enrollment_id"),
            budget_month=data.get("budget_month"),
            now=now,
        )
        _prefill_income_from_source(budget_id, resident.get("enrollment_id"), now)
        _refresh_active_budget_session_for_resident(resident_id)

    flash(f"{_format_budget_month(data.get('budget_month'))} budget created.", "success")
    return redirect(
        url_for(
            "case_management.edit_budget_session",
            resident_id=resident_id,
            budget_id=budget_id,
        )
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
        SELECT id
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
        db_execute("DELETE FROM resident_budget_line_items WHERE budget_session_id = ?", (budget_id,))
        db_execute(
            "DELETE FROM resident_budget_sessions WHERE id = ? AND resident_id = ?",
            (budget_id, resident_id),
        )
        _refresh_active_budget_session_for_resident(resident_id)

    flash("Budget month deleted.", "success")
    return redirect(url_for("case_management.budget_sessions", resident_id=resident_id))


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

    budget_row = dict(row)
    now = utcnow_iso()
    _create_default_line_items(budget_id, now)

    if request.method == "POST":
        action = clean(request.form.get("action"))
        line_item_lookup = _load_budget_line_item_lookup(budget_id)
        can_edit_future_budget = _is_future_budget_month(budget_row.get("budget_month"))

        if action == "add_transaction":
            transaction_date = clean(request.form.get("transaction_date"))
            line_item_id = _safe_positive_int(request.form.get("line_item_id"))
            amount_raw = request.form.get("amount")
            merchant_or_note = clean(request.form.get("merchant_or_note"))

            errors, amount = _validate_transaction_inputs(
                budget_row=budget_row,
                line_item_lookup=line_item_lookup,
                transaction_date=transaction_date,
                line_item_id=line_item_id,
                amount_raw=amount_raw,
            )
            if errors:
                for error_text in errors:
                    flash(error_text, "error")
            else:
                with db_transaction():
                    db_execute(
                        """
                        INSERT INTO resident_budget_transactions (
                            budget_session_id,
                            resident_id,
                            enrollment_id,
                            line_item_id,
                            transaction_date,
                            amount,
                            merchant_or_note,
                            entered_by_role,
                            entered_by_staff_user_id,
                            created_at,
                            updated_at,
                            is_deleted
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            budget_id,
                            resident_id,
                            resident.get("enrollment_id"),
                            line_item_id,
                            transaction_date,
                            amount,
                            merchant_or_note or None,
                            "staff",
                            session.get("staff_user_id"),
                            now,
                            now,
                            False if g.get("db_kind") == "pg" else 0,
                        ),
                    )
                flash("Transaction added.", "success")

            return redirect(
                url_for(
                    "case_management.edit_budget_session",
                    resident_id=resident_id,
                    budget_id=budget_id,
                )
            )

        if action == "edit_transaction":
            transaction_id = _safe_positive_int(request.form.get("transaction_id"))
            transaction_date = clean(request.form.get("transaction_date"))
            line_item_id = _safe_positive_int(request.form.get("line_item_id"))
            amount_raw = request.form.get("amount")
            merchant_or_note = clean(request.form.get("merchant_or_note"))

            transaction_row = _load_staff_transaction(
                transaction_id or 0,
                budget_id,
                resident_id,
            )
            if not transaction_row:
                flash("Transaction not found for this budget month.", "error")
                return redirect(
                    url_for(
                        "case_management.edit_budget_session",
                        resident_id=resident_id,
                        budget_id=budget_id,
                    )
                )

            errors, amount = _validate_transaction_inputs(
                budget_row=budget_row,
                line_item_lookup=line_item_lookup,
                transaction_date=transaction_date,
                line_item_id=line_item_id,
                amount_raw=amount_raw,
            )
            if errors:
                for error_text in errors:
                    flash(error_text, "error")
            else:
                with db_transaction():
                    db_execute(
                        """
                        UPDATE resident_budget_transactions
                        SET line_item_id = ?,
                            transaction_date = ?,
                            amount = ?,
                            merchant_or_note = ?,
                            edited_at = ?,
                            edited_by_role = ?,
                            edited_by_staff_user_id = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            line_item_id,
                            transaction_date,
                            amount,
                            merchant_or_note or None,
                            now,
                            "staff",
                            session.get("staff_user_id"),
                            now,
                            transaction_id,
                        ),
                    )
                flash("Transaction updated.", "success")

            return redirect(
                url_for(
                    "case_management.edit_budget_session",
                    resident_id=resident_id,
                    budget_id=budget_id,
                )
            )

        if action == "delete_transaction":
            transaction_id = _safe_positive_int(request.form.get("transaction_id"))
            transaction_row = _load_staff_transaction(
                transaction_id or 0,
                budget_id,
                resident_id,
            )

            if not transaction_row:
                flash("Transaction not found for this budget month.", "error")
            else:
                with db_transaction():
                    db_execute(
                        """
                        UPDATE resident_budget_transactions
                        SET is_deleted = ?,
                            deleted_at = ?,
                            deleted_by_role = ?,
                            deleted_by_staff_user_id = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            True if g.get("db_kind") == "pg" else 1,
                            now,
                            "staff",
                            session.get("staff_user_id"),
                            now,
                            transaction_id,
                        ),
                    )
                flash("Transaction deleted.", "success")

            return redirect(
                url_for(
                    "case_management.edit_budget_session",
                    resident_id=resident_id,
                    budget_id=budget_id,
                )
            )

        with db_transaction():
            if can_edit_future_budget:
                _update_future_budget_line_items_only(budget_id, now)
                flash("Budget updated.", "success")
            else:
                flash(
                    "This budget month is already live. Use transactions to reconcile "
                    "resident spending instead of changing the budget plan.",
                    "error",
                )

            db_execute(
                """
                UPDATE resident_budget_sessions
                SET notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (clean(request.form.get("notes")), now, budget_id),
            )

        return redirect(
            url_for(
                "case_management.edit_budget_session",
                resident_id=resident_id,
                budget_id=budget_id,
            )
        )

    _refresh_active_budget_session_for_resident(resident_id)

    page_context = _build_budget_page_context(resident_id)
    editor_context = _build_budget_editor_context(budget_id, budget_row.get("budget_month"))
    budget_row["budget_month_label"] = _format_budget_month(budget_row.get("budget_month"))

    return render_template(
        "case_management/edit_budget_session.html",
        resident=resident,
        budget_row=budget_row,
        **page_context,
        **editor_context,
    )


def print_budget_view(resident_id: int, budget_id: int):
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

    budget_row = dict(row)
    budget_row["budget_month_label"] = _format_budget_month(budget_row.get("budget_month"))

    editor_context = _build_budget_editor_context(budget_id, budget_row.get("budget_month"))
    income_items = editor_context.get("income_items") or []
    expense_items = (editor_context.get("expense_left_items") or []) + (
        editor_context.get("expense_right_items") or []
    )

    income_left = [
        {
            "label": item.get("line_label"),
            "amount": item.get("projected_amount") or 0,
        }
        for item in income_items[:3]
    ]
    income_right = [
        {
            "label": item.get("line_label"),
            "amount": item.get("projected_amount") or 0,
        }
        for item in income_items[3:]
    ]
    expenses = [
        {
            "label": item.get("line_label"),
            "budget": item.get("projected_amount") or 0,
            "actual": item.get("actual_amount") or 0,
            "diff": item.get("difference_amount") or 0,
        }
        for item in expense_items
    ]

    resident_name = " ".join(
        part for part in [resident.get("first_name"), resident.get("last_name")] if part
    ).strip()

    return render_template(
        "case_management/print_budget.html",
        resident=resident,
        resident_name=resident_name,
        budget_row=budget_row,
        total_income=editor_context.get("total_income") or 0,
        total_expenses=editor_context.get("total_expenses") or 0,
        balance=editor_context.get("balance") or 0,
        income_left=income_left,
        income_right=income_right,
        expenses=expenses,
        budget_month=budget_row.get("budget_month_label"),
    )
