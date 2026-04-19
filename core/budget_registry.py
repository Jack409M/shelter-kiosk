from __future__ import annotations

from typing import Iterable

BUDGET_LINE_ITEM_REGISTRY: tuple[dict[str, object], ...] = (
    {"line_group": "income", "line_key": "net_employment", "line_label": "Net Employment", "is_resident_visible": True},
    {"line_group": "income", "line_key": "net_ss_ssi_ssdi", "line_label": "SS SSI SSDI Survivor Benefits", "is_resident_visible": True},
    {"line_group": "income", "line_key": "tanf", "line_label": "TANF", "is_resident_visible": True},
    {"line_group": "income", "line_key": "child_support", "line_label": "Child Support", "is_resident_visible": True},
    {"line_group": "income", "line_key": "alimony", "line_label": "Alimony", "is_resident_visible": True},
    {"line_group": "income", "line_key": "cash_gift", "line_label": "Cash Gift", "is_resident_visible": True},
    {"line_group": "income", "line_key": "other_income", "line_label": "Other", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "rent", "line_label": "Rent", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "soap_hygiene", "line_label": "Soap Hygiene", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "cigarettes", "line_label": "Cigarettes", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "prescription", "line_label": "Prescription", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "hospital_doctor", "line_label": "Hospital Dr.", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "dental", "line_label": "Dental", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "cell_phone", "line_label": "Cell Phone", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "car_payment", "line_label": "Car Payment", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "car_insurance", "line_label": "Car Insurance", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "car_maintenance", "line_label": "Car Maintenance", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "gasoline", "line_label": "Gasoline", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "bus_taxi_lyft_uber", "line_label": "Bus Taxi Lyft Uber", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "probation_fees", "line_label": "Probation Fees", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "court_fees", "line_label": "Court Fees", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "driver_license_surcharge", "line_label": "Driver License Surcharge", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "student_loan", "line_label": "Student Loan", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "loan_payment", "line_label": "Loan Payment", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "child_care", "line_label": "Child Care", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "tithe", "line_label": "Tithe", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "entertainment", "line_label": "Entertainment", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "streamed_media", "line_label": "Streamed Media", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "bank_fees", "line_label": "Bank Fees", "is_resident_visible": True},
    {"line_group": "expense", "line_key": "savings", "line_label": "Savings", "is_resident_visible": True},
)


def budget_line_item_definitions() -> tuple[dict[str, object], ...]:
    return BUDGET_LINE_ITEM_REGISTRY


def iter_budget_line_item_definitions() -> Iterable[dict[str, object]]:
    for item in BUDGET_LINE_ITEM_REGISTRY:
        yield dict(item)


def budget_line_item_definition_map() -> dict[str, dict[str, object]]:
    return {str(item["line_key"]): dict(item) for item in BUDGET_LINE_ITEM_REGISTRY}


def is_budget_expense_key(line_key: str | None) -> bool:
    key = str(line_key or "").strip()
    item = budget_line_item_definition_map().get(key)
    return bool(item and str(item.get("line_group") or "").strip().lower() == "expense")


def is_budget_income_key(line_key: str | None) -> bool:
    key = str(line_key or "").strip()
    item = budget_line_item_definition_map().get(key)
    return bool(item and str(item.get("line_group") or "").strip().lower() == "income")


__all__ = [
    "BUDGET_LINE_ITEM_REGISTRY",
    "budget_line_item_definition_map",
    "budget_line_item_definitions",
    "is_budget_expense_key",
    "is_budget_income_key",
    "iter_budget_line_item_definitions",
]
