from __future__ import annotations

from datetime import date
from typing import Any

from flask import g, session

from core.db import db_fetchone


CASE_MANAGER_ROLES = {
    "admin",
    "shelter_director",
    "case_manager",
}


def _db_placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _clean_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def placeholder() -> str:
    return _db_placeholder()


def case_manager_allowed() -> bool:
    return session.get("role") in CASE_MANAGER_ROLES


def normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def shelter_equals_sql(column_name: str) -> str:
    return f"LOWER(COALESCE({column_name}, '')) = {placeholder()}"


def current_enrollment_order_sql(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return (
        f"CASE WHEN COALESCE({prefix}program_status, '') = 'active' THEN 0 ELSE 1 END, "
        f"COALESCE({prefix}entry_date, '') DESC, "
        f"{prefix}id DESC"
    )


def fetch_current_enrollment_for_resident(
    resident_id: int,
    columns: str = "*",
) -> dict[str, Any] | tuple[Any, ...] | None:
    ph = placeholder()

    return db_fetchone(
        f"""
        SELECT {columns}
        FROM program_enrollments
        WHERE resident_id = {ph}
        ORDER BY {current_enrollment_order_sql()}
        LIMIT 1
        """,
        (resident_id,),
    )


def fetch_current_enrollment_id_for_resident(resident_id: int) -> int | None:
    row = fetch_current_enrollment_for_resident(resident_id, columns="id")
    if not row:
        return None

    if isinstance(row, dict):
        raw_id = row.get("id")
        return int(raw_id) if raw_id is not None else None

    raw_id = row[0] if len(row) > 0 else None
    return int(raw_id) if raw_id is not None else None


def resident_has_active_enrollment(resident_id: int) -> bool:
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT id
        FROM program_enrollments
        WHERE resident_id = {ph}
          AND program_status = {ph}
        LIMIT 1
        """,
        (resident_id, "active"),
    )
    return bool(row)


def clean(value: str | None) -> str | None:
    return _clean_text(value)


def digits_only(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def parse_iso_date(value: str | None) -> date | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None

    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None

    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_money(value: str | None) -> float | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None

    normalized = cleaned.replace("$", "").replace(",", "")
    try:
        return float(normalized)
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
    first_name = _clean_text(form.get("first_name")) or ""
    last_name = _clean_text(form.get("last_name")) or ""
    full_name = f"{first_name} {last_name}".strip()
    return full_name or "Unnamed intake draft"
