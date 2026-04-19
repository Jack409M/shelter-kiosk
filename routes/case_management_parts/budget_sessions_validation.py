from __future__ import annotations

import re
from typing import Any, Mapping

from routes.case_management_parts.helpers import clean, parse_iso_date, parse_money

_BUDGET_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

_MONEY_FIELDS = (
    "projected_total_income",
    "actual_total_income",
    "projected_total_expenses",
    "actual_total_expenses",
    "projected_remaining_income",
    "actual_remaining_income",
    "last_month_savings",
    "this_month_savings",
    "house_contribution_amount",
    "personal_amount",
    "amount_left_for_abba",
)


def _parse_optional_money(form: Mapping[str, Any], field_name: str, label: str, errors: list[str]) -> float | None:
    raw_value = clean(form.get(field_name))
    if not raw_value:
        return None

    parsed_value = parse_money(raw_value)
    if parsed_value is None:
        errors.append(f"{label} must be a valid amount.")
        return None

    return round(parsed_value, 2)


def _resolve_budget_month(session_date_iso: str | None, budget_month_text: str | None, errors: list[str]) -> str | None:
    if budget_month_text:
        if not _BUDGET_MONTH_RE.match(budget_month_text):
            errors.append("Budget month must use YYYY-MM format.")
            return None
        return budget_month_text

    if session_date_iso:
        return session_date_iso[:7]

    return None


def _resolve_remaining(income_value: float | None, expense_value: float | None, submitted_value: float | None) -> float | None:
    if submitted_value is not None:
        return round(submitted_value, 2)

    if income_value is None and expense_value is None:
        return None

    income_amount = income_value or 0.0
    expense_amount = expense_value or 0.0
    return round(income_amount - expense_amount, 2)


def validate_budget_session_form(form: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []

    session_date_text = clean(form.get("session_date"))
    session_date_iso = None

    if not session_date_text:
        errors.append("Budget session date is required.")
    else:
        parsed_date = parse_iso_date(session_date_text)
        if parsed_date is None:
            errors.append("Budget session date must be a valid date.")
        else:
            session_date_iso = parsed_date.isoformat()

    budget_month_text = clean(form.get("budget_month"))
    budget_month = _resolve_budget_month(session_date_iso, budget_month_text, errors)

    data: dict[str, Any] = {
        "session_date": session_date_iso,
        "budget_month": budget_month,
        "notes": clean(form.get("notes")),
    }

    labels = {
        "projected_total_income": "Projected total income",
        "actual_total_income": "Actual total income",
        "projected_total_expenses": "Projected total expenses",
        "actual_total_expenses": "Actual total expenses",
        "projected_remaining_income": "Projected remaining income",
        "actual_remaining_income": "Actual remaining income",
        "last_month_savings": "Last month savings",
        "this_month_savings": "This month savings",
        "house_contribution_amount": "House contribution amount",
        "personal_amount": "Personal amount",
        "amount_left_for_abba": "Amount left for Abba",
    }

    for field_name in _MONEY_FIELDS:
        data[field_name] = _parse_optional_money(form, field_name, labels[field_name], errors)

    data["projected_remaining_income"] = _resolve_remaining(
        data["projected_total_income"],
        data["projected_total_expenses"],
        data["projected_remaining_income"],
    )
    data["actual_remaining_income"] = _resolve_remaining(
        data["actual_total_income"],
        data["actual_total_expenses"],
        data["actual_remaining_income"],
    )

    return data, errors


__all__ = ["validate_budget_session_form"]
