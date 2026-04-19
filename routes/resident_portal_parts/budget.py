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
            if not budget or budget_id is None:
                flash("No active budget found. Please see your case manager.", "error")
                return redirect(url_for("resident_portal.resident_budget"))

            if not line_item_lookup:
                _ensure_budget_line_items_exist(budget_id)
                line_item_lookup = _load_budget_line_item_lookup(budget_id)

            transaction_date = _clean_text(request.form.get("transaction_date"))
            line_item_id = _safe_int(request.form.get("line_item_id"))
            amount_raw = request.form.get("amount")
            merchant_or_note = _clean_text(request.form.get("merchant_or_note"))

            errors: list[str] = []

            if not transaction_date:
                errors.append("Transaction date is required.")
            elif len(transaction_date) != 10:
                errors.append("Transaction date must be valid.")

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

            if errors:
                for error in errors:
                    flash(error, "error")
            else:
                now = utcnow_iso()
                current_actual = selected_item.get("actual_amount")
                current_actual_value = float(current_actual) if current_actual is not None else 0.0

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
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
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

                    db_execute(
                        _sql(
                            """
                            UPDATE resident_budget_line_items
                            SET actual_amount = %s,
                                updated_at = %s
                            WHERE id = %s
                            """,
                            """
                            UPDATE resident_budget_line_items
                            SET actual_amount = ?,
                                updated_at = ?
                            WHERE id = ?
                            """,
                        ),
                        (round(current_actual_value + amount, 2), now, line_item_id),
                    )

                flash("Purchase added.", "success")
                return redirect(url_for("resident_portal.resident_budget"))

        income_items, expense_items = _load_budget_line_items_with_status(budget_id)
        recent_transactions = _load_recent_budget_transactions(budget_id)

        return render_template(
            "resident/budget.html",
            budget=budget,
            income_items=income_items,
            expense_items=expense_items,
            recent_transactions=recent_transactions,
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
