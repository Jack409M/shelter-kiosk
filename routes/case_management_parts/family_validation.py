from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from routes.case_management_parts.helpers import (
    clean,
    parse_int,
    parse_money,
)

CURRENT_YEAR = date.today().year


def _yes_no_to_bool(value: str | None) -> bool | None:
    normalized = (value or "").strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _validate_birth_year(value: str | None, errors: list[str]) -> int | None:
    parsed = parse_int(value)

    if value and parsed is None:
        errors.append("Birth Year must be a valid number.")
        return None

    if parsed is not None and (parsed < 1900 or parsed > CURRENT_YEAR):
        errors.append("Birth Year must be a reasonable year.")
    return parsed


def _validate_money(value: str | None, label: str, errors: list[str]) -> float | None:
    parsed = parse_money(value)

    if value and parsed is None:
        errors.append(f"{label} must be a valid dollar amount.")
        return None

    if parsed is not None and parsed < 0:
        errors.append(f"{label} cannot be negative.")

    return parsed


def validate_child_form(form: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    data = {
        "child_name": clean(form.get("child_name")),
        "birth_year": form.get("birth_year"),
        "relationship": clean(form.get("relationship")),
        "living_status": clean(form.get("living_status")),
        "receives_survivor_benefit": form.get("receives_survivor_benefit"),
        "survivor_benefit_amount": form.get("survivor_benefit_amount"),
        "survivor_benefit_notes": clean(form.get("survivor_benefit_notes")),
        "child_support_amount": form.get("child_support_amount"),
        "child_support_notes": clean(form.get("child_support_notes")),
    }

    errors: list[str] = []

    if not data["child_name"]:
        errors.append("Child name is required.")

    data["birth_year"] = _validate_birth_year(data["birth_year"], errors)

    data["receives_survivor_benefit"] = _yes_no_to_bool(data.get("receives_survivor_benefit"))

    data["survivor_benefit_amount"] = _validate_money(
        data.get("survivor_benefit_amount"),
        "Survivor Benefit Amount",
        errors,
    )

    data["child_support_amount"] = _validate_money(
        data.get("child_support_amount"),
        "Child Support Amount",
        errors,
    )

    if not data["receives_survivor_benefit"]:
        data["survivor_benefit_amount"] = None
        data["survivor_benefit_notes"] = None

    return data, errors


def _parse_service_date(value: str | None, errors: list[str]) -> str | None:
    value = clean(value)
    if not value:
        return None

    try:
        datetime.fromisoformat(value)
    except ValueError:
        errors.append("Service date must be valid.")
        return None

    return value


def validate_child_service_form(
    form: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    data = {
        "service_type": clean(form.get("service_type")),
        "service_type_other": clean(form.get("service_type_other")),
        "outcome": clean(form.get("outcome")),
        "quantity": form.get("quantity"),
        "unit": clean(form.get("unit")),
        "notes": clean(form.get("notes")),
        "service_date": form.get("service_date"),
    }

    errors: list[str] = []

    service_type = data["service_type"]
    if service_type and service_type.lower() == "other":
        service_type = data["service_type_other"] or service_type

    if data["service_type_other"] and not data["service_type"]:
        service_type = data["service_type_other"]

    if not service_type:
        errors.append("Service type is required.")

    data["service_type"] = service_type

    quantity = parse_int(data.get("quantity"))
    if data.get("quantity") and quantity is None:
        errors.append("Quantity must be a whole number.")
    if quantity is not None and quantity < 0:
        errors.append("Quantity cannot be negative.")
    data["quantity"] = quantity

    data["service_date"] = _parse_service_date(
        data.get("service_date"),
        errors,
    )

    return data, errors
