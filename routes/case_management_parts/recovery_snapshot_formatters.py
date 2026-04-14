from __future__ import annotations

from datetime import date
from datetime import datetime
from typing import Any


EMPTY_DISPLAY = "—"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def parse_dateish(value: Any):
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def days_since(value: Any):
    parsed = parse_dateish(value)
    if not parsed:
        return None

    return max((date.today() - parsed).days, 0)


def money_display(value: Any) -> str:
    if value in (None, ""):
        return EMPTY_DISPLAY

    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)

    return f"${amount:,.2f}"


def bool_display(value: Any) -> str:
    if value is None:
        return EMPTY_DISPLAY
    return "Yes" if bool(value) else "No"


def employment_status_display(value: Any) -> str:
    normalized = _clean_text(value).lower()

    if not normalized:
        return EMPTY_DISPLAY
    if normalized == "employed":
        return "Employed"
    if normalized == "unemployed":
        return "Unemployed"

    return str(value)


def employment_type_display(value: Any) -> str:
    normalized = _clean_text(value).lower()

    if not normalized:
        return EMPTY_DISPLAY
    if normalized == "full_time":
        return "Full Time"
    if normalized == "part_time":
        return "Part Time"

    return str(value).replace("_", " ").title()


def result_display(value: Any) -> str:
    normalized = _clean_text(value)
    return normalized or EMPTY_DISPLAY
