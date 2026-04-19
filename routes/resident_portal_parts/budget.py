from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, url_for

from core.access import require_resident
from core.db import db_execute, db_transaction
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

        if request.method == "POST":
            action = _clean_text(request.form.get("action"))
            now = utcnow_iso()

            if action == "delete_transaction":
                tx_id = _safe_int(request.form.get("transaction_id"))
                if tx_id:
                    with db_transaction():
                        db_execute(
                            _sql(
                                "UPDATE resident_budget_transactions SET is_deleted = TRUE, deleted_at = %s, deleted_by_role = %s, deleted_by_resident_id = %s WHERE id = %s",
                                "UPDATE resident_budget_transactions SET is_deleted = 1, deleted_at = ?, deleted_by_role = ?, deleted_by_resident_id = ? WHERE id = ?",
                            ),
                            (now, "resident", resident_id, tx_id),
                        )
                    flash("Transaction removed.", "success")
                return redirect(url_for("resident_portal.resident_budget"))

            if action == "edit_transaction":
                tx_id = _safe_int(request.form.get("transaction_id"))
                amount_raw = request.form.get("amount")
                merchant = _clean_text(request.form.get("merchant_or_note"))

                try:
                    amount = float(str(amount_raw or "").replace("$", "").replace(",", "").strip())
                except Exception:
                    amount = None

                if tx_id and amount and amount > 0:
                    with db_transaction():
                        db_execute(
                            _sql(
                                "UPDATE resident_budget_transactions SET amount = %s, merchant_or_note = %s, edited_at = %s, edited_by_role = %s, edited_by_resident_id = %s WHERE id = %s",
                                "UPDATE resident_budget_transactions SET amount = ?, merchant_or_note = ?, edited_at = ?, edited_by_role = ?, edited_by_resident_id = ? WHERE id = ?",
                            ),
                            (round(amount, 2), merchant or None, now, "resident", resident_id, tx_id),
                        )
                    flash("Transaction updated.", "success")
                else:
                    flash("Invalid transaction update.", "error")
                return redirect(url_for("resident_portal.resident_budget"))

            # default = add
            transaction_date = _clean_text(request.form.get("transaction_date"))
            line_item_id = _safe_int(request.form.get("line_item_id"))
            amount_raw = request.form.get("amount")
            merchant_or_note = _clean_text(request.form.get("merchant_or_note"))

            errors: list[str] = []

            if not transaction_date or len(transaction_date) != 10:
                errors.append("Transaction date must be valid.")

            try:
                amount = float(str(amount_raw or "").replace("$", "").replace(",", "").strip())
            except ValueError:
                amount = None

            if amount is None or amount <= 0:
                errors.append("Amount must be greater than zero.")

            selected_item = line_item_lookup.get(line_item_id or 0)
            if not selected_item or str(selected_item.get("line_group") or "").strip().lower() != "expense":
                errors.append("Please select a valid expense category.")

            if errors:
                for error in errors:
                    flash(error, "error")
            else:
                with db_transaction():
                    db_execute(
                        _sql(
                            "INSERT INTO resident_budget_transactions (budget_session_id, resident_id, enrollment_id, line_item_id, transaction_date, amount, merchant_or_note, entered_by_role, entered_by_resident_id, created_at, updated_at, is_deleted) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            "INSERT INTO resident_budget_transactions (budget_session_id, resident_id, enrollment_id, line_item_id, transaction_date, amount, merchant_or_note, entered_by_role, entered_by_resident_id, created_at, updated_at, is_deleted) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        ),
                        (
                            budget_id,
                            resident_id,
                            budget.get("enrollment_id"),
                            line_item_id,
                            transaction_date,
                            round(amount, 2),
                            merchant_or_note or None,
                            "resident",
                            resident_id,
                            now,
                            now,
                            False,
                        ),
                    )

                flash("Purchase added.", "success")
                return redirect(url_for("resident_portal.resident_budget"))

        income_items, expense_items = _load_budget_line_items_with_status(budget_id)
        recent_transactions = _load_recent_budget_transactions(budget_id)

        total_budgeted = sum(item.get("projected_value", 0.0) for item in expense_items)
        total_spent = sum(item.get("actual_value", 0.0) for item in expense_items)
        total_remaining = total_budgeted - total_spent

        return render_template(
            "resident/budget.html",
            budget=budget,
            income_items=income_items,
            expense_items=expense_items,
            recent_transactions=recent_transactions,
            total_budgeted=round(total_budgeted, 2),
            total_spent=round(total_spent, 2),
            total_remaining=round(total_remaining, 2),
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
