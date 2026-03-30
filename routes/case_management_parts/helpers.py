from __future__ import annotations

from datetime import date
from typing import Any

from flask import g
from flask import session


def case_manager_allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def shelter_equals_sql(column_name: str) -> str:
    if g.get("db_kind") == "pg":
        return f"LOWER(COALESCE({column_name}, '')) = %s"
    return f"LOWER(COALESCE({column_name}, '')) = ?"


def placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def digits_only(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def parse_iso_date(value: str | None) -> date | None:
    value = clean(value)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    value = clean(value)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_money(value: str | None) -> float | None:
    value = clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def yes_no_to_int(value: str | None) -> int | None:
    normalized = (value or "").strip().lower()
    if normalized == "yes":
        return 1
    if normalized == "no":
        return 0
    return None


def draft_display_name(form: Any) -> str:
    first_name = clean(form.get("first_name")) or ""
    last_name = clean(form.get("last_name")) or ""
    full_name = f"{first_name} {last_name}".strip()
    return full_name or "Unnamed intake draft"
