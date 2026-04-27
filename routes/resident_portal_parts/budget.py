from __future__ import annotations

from datetime import datetime

from flask import current_app, flash, redirect, render_template, request, url_for

from core.access import require_resident
from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from routes.resident_portal import resident_portal
from routes.resident_portal_parts.helpers import (
    _clean_text,
    _clear_resident_session,
    _ensure_budget_line_items_exist,
    _load_budget_line_item_lookup,
    _load_budget_line_items_with_status,
    _load_current_budget_session,
    _load_recent_budget_transactions,
    _prepare_resident_request_context,
    _resident_signin_redirect,
    _safe_int,
    _sql,
)


def _parse_transaction_date(date_text: str) -> datetime | None:
    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return None


def _budget_month_bounds(budget: dict | None) -> tuple[str | None, str | None]:
    budget_month = str((budget or {}).get("budget_month") or "").strip()
    if not budget_month:
        return None, None

    try:
        month_start = datetime.strptime(f"{budget_month}-01", "%Y-%m-%d")
    except ValueError:
        return None, None

    if month_start.month == 12:
        next_month = datetime(month_start.year + 1, 1, 1)
    else:
        next_month = datetime(month_start.year, month_start.month + 1, 1)

    month_end = next_month.replace(day=1) - (next_month - next_month.replace(day=1))
    return month_start.strftime("%Y-%m-%d"), month_end.strftime("%Y-%m-%d")


def _validate_transaction_inputs(
    *,
    budget: dict,
    line_item_lookup: dict[int, dict],
    transaction_date: str,
    line_item_id: int | None,
    amount_raw: str | None,
) -> tuple[list[str], float | None, dict | None]:
    errors: list[str] = []

    parsed_date = _parse_transaction_date(transaction_date)
    if parsed_date is None:
        errors.append("Transaction date must be a valid date.")

    amount = None
    try:
        amount = float(str(amount_raw or "").replace("$", "").replace(",", "").strip())
    except ValueError:
        amount = None

    if amount is None or amount <= 0:
        errors.append("Amount must be greater than zero.")

    selected_item = line_item_lookup.get(line_item_id or 0)
    if not selected_item:
        errors.append("Please select a valid budget category.")
    elif str(selected_item.get("line_group") or "").strip().lower() != "expense":
        errors.append("Spending can only be logged to an expense category.")
    elif int(selected_item.get("budget_session_id") or 0) != int(budget.get("id") or 0):
        errors.append("Budget category does not belong to this budget month.")

    month_start, month_end = _budget_month_bounds(budget)
    if (
        parsed_date is not None
        and month_start
        and month_end
        and not (month_start <= transaction_date <= month_end)
    ):
        errors.append(
            f"Transaction date must stay inside this budget month. Allowed range: {month_start} to {month_end}."
        )

    return errors, (round(amount, 2) if amount is not None else None), selected_item


def _load_owned_transaction(transaction_id: int, budget_id: int, resident_id: int):
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


@resident_portal.route("/resident/budget", methods=["GET", "POST"])
@require_resident
def resident_budget():
    resident_id = None
    shelter = ""

    try:
        resident_id, shelter, _resident_identifier = _prepare_resident_request_context()

        if resident_id is None:
            return _resident_signin_redirect()

        budget = _load_current_budget_session(resident_id)
        budget_id = _safe_int(budget.get("id")) if budget else None

        if budget_id is not None:
            _ensure_budget_line_items_exist(budget_id)

        line_item_lookup = _load_budget_line_item_lookup(budget_id)
        selected_line_item_id = _safe_int(request.args.get("line_item_id"))

        if request.method == "POST":
            if not budget or budget_id is None:
                flash("No active budget found. Please see your case manager.", "error")
                return redirect(url_for("resident_portal.resident_budget"))

            action = _clean_text(request.form.get("action"))
            now = utcnow_iso()

            if action == "delete_transaction":
                tx_id = _safe_int(request.form.get("transaction_id"))
                if not tx_id:
                    flash("Transaction not found.", "error")
                    return redirect(
                        url_for("resident_portal.resident_budget") + "#transaction-entry"
                    )

                transaction_row = _load_owned_transaction(tx_id, budget_id, resident_id)
                if not transaction_row:
                    flash("Transaction not found for this budget.", "error")
                    return redirect(
                        url_for("resident_portal.resident_budget") + "#transaction-entry"
                    )

                with db_transaction():
                    db_execute(
                        _sql(
                            "UPDATE resident_budget_transactions SET is_deleted = TRUE, deleted_at = %s, deleted_by_role = %s, deleted_by_resident_id = %s, updated_at = %s WHERE id = %s",
                            "UPDATE resident_budget_transactions SET is_deleted = 1, deleted_at = ?, deleted_by_role = ?, deleted_by_resident_id = ?, updated_at = ? WHERE id = ?",
                        ),
                        (now, "resident", resident_id, now, tx_id),
                    )
                flash("Transaction removed.", "success")
                return redirect(url_for("resident_portal.resident_budget") + "#transaction-entry")

            if action == "edit_transaction":
                tx_id = _safe_int(request.form.get("transaction_id"))
                if not tx_id:
                    flash("Transaction not found.", "error")
                    return redirect(
                        url_for("resident_portal.resident_budget") + "#transaction-entry"
                    )

                transaction_row = _load_owned_transaction(tx_id, budget_id, resident_id)
                if not transaction_row:
                    flash("Transaction not found for this budget.", "error")
                    return redirect(
                        url_for("resident_portal.resident_budget") + "#transaction-entry"
                    )

                transaction_date = _clean_text(request.form.get("transaction_date"))
                line_item_id = _safe_int(request.form.get("line_item_id"))
                amount_raw = request.form.get("amount")
                merchant_or_note = _clean_text(request.form.get("merchant_or_note"))

                errors, amount, _selected_item = _validate_transaction_inputs(
                    budget=budget,
                    line_item_lookup=line_item_lookup,
                    transaction_date=transaction_date,
                    line_item_id=line_item_id,
                    amount_raw=amount_raw,
                )

                if errors:
                    for error in errors:
                        flash(error, "error")
                    return redirect(
                        url_for(
                            "resident_portal.resident_budget",
                            line_item_id=line_item_id or transaction_row["line_item_id"],
                        )
                        + "#transaction-entry"
                    )

                with db_transaction():
                    db_execute(
                        _sql(
                            """
                            UPDATE resident_budget_transactions
                            SET line_item_id = %s,
                                transaction_date = %s,
                                amount = %s,
                                merchant_or_note = %s,
                                edited_at = %s,
                                edited_by_role = %s,
                                edited_by_resident_id = %s,
                                updated_at = %s
                            WHERE id = %s
                            """,
                            """
                            UPDATE resident_budget_transactions
                            SET line_item_id = ?,
                                transaction_date = ?,
                                amount = ?,
                                merchant_or_note = ?,
                                edited_at = ?,
                                edited_by_role = ?,
                                edited_by_resident_id = ?,
                                updated_at = ?
                            WHERE id = ?
                            """,
                        ),
                        (
                            line_item_id,
                            transaction_date,
                            amount,
                            merchant_or_note or None,
                            now,
                            "resident",
                            resident_id,
                            now,
                            tx_id,
                        ),
                    )
                flash("Transaction updated.", "success")
                return redirect(
                    url_for("resident_portal.resident_budget", line_item_id=line_item_id)
                    + "#transaction-entry"
                )

            transaction_date = _clean_text(request.form.get("transaction_date"))
            line_item_id = _safe_int(request.form.get("line_item_id"))
            amount_raw = request.form.get("amount")
            merchant_or_note = _clean_text(request.form.get("merchant_or_note"))

            errors, amount, _selected_item = _validate_transaction_inputs(
                budget=budget,
                line_item_lookup=line_item_lookup,
                transaction_date=transaction_date,
                line_item_id=line_item_id,
                amount_raw=amount_raw,
            )

            if errors:
                for error in errors:
                    flash(error, "error")
                return redirect(
                    url_for("resident_portal.resident_budget", line_item_id=line_item_id)
                    + "#transaction-entry"
                )

            with db_transaction():
                db_execute(
                    _sql(
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
                            entered_by_resident_id,
                            created_at,
                            updated_at,
                            is_deleted
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
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
                            entered_by_resident_id,
                            created_at,
                            updated_at,
                            is_deleted
                        )
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                    ),
                    (
                        budget_id,
                        resident_id,
                        budget.get("enrollment_id"),
                        line_item_id,
                        transaction_date,
                        amount,
                        merchant_or_note or None,
                        "resident",
                        resident_id,
                        now,
                        now,
                        False,
                    ),
                )
            flash("Purchase added.", "success")
            return redirect(
                url_for("resident_portal.resident_budget", line_item_id=line_item_id)
                + "#transaction-entry"
            )

        _income_items, expense_items = _load_budget_line_items_with_status(budget_id)
        recent_transactions = _load_recent_budget_transactions(budget_id)

        total_budgeted = sum(item.get("projected_value", 0.0) for item in expense_items)
        total_spent = sum(item.get("actual_value", 0.0) for item in expense_items)
        total_remaining = total_budgeted - total_spent
        month_start, month_end = _budget_month_bounds(budget)

        if selected_line_item_id is None and expense_items:
            selected_line_item_id = expense_items[0]["id"]

        selected_line_item = next(
            (
                item
                for item in expense_items
                if int(item.get("id") or 0) == int(selected_line_item_id or 0)
            ),
            None,
        )

        return render_template(
            "resident/budget.html",
            budget=budget,
            expense_items=expense_items,
            recent_transactions=recent_transactions,
            total_budgeted=round(total_budgeted, 2),
            total_spent=round(total_spent, 2),
            total_remaining=round(total_remaining, 2),
            budget_month_start=month_start,
            budget_month_end=month_end,
            selected_line_item=selected_line_item,
            selected_line_item_id=selected_line_item_id,
        )
    except Exception as exc:
        current_app.logger.exception(
            "resident_budget_failed resident_id=%s shelter=%s exception_type=%s",
            resident_id if resident_id is not None else "unknown",
            shelter or "unknown",
            type(exc).__name__,
        )
        _clear_resident_session()
        return _resident_signin_redirect()
