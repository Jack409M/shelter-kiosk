from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.db import db_execute, db_fetchall, db_fetchone, get_db
from core.kiosk_activity_categories import (
    AA_NA_PARENT_ACTIVITY_KEY,
    VOLUNTEER_PARENT_ACTIVITY_KEY,
    LOCKED_PARENT_ACTIVITY_DEFINITIONS,
    load_active_kiosk_activity_child_options_for_shelter,
    load_kiosk_activity_categories_for_shelter,
)
from core.pass_retention import run_pass_retention_cleanup_for_shelter
from core.pass_rules import CHICAGO_TZ, pass_type_label
from core.helpers import utcnow_iso
from core.resident_portal_service import chi_today_str, complete_chore, get_today_chores
from routes.attendance_parts.helpers import to_local

resident_portal = Blueprint("resident_portal", __name__)

LEGACY_ACTIVITY_LABEL_TO_PARENT_ACTIVITY_KEY = {
    "rad": "program",
    "doctor appointment": "medical_health",
    "counseling": "medical_health",
    "school": "education",
    "legal obligation": "legal",
}


def _clear_resident_session() -> None:
    session.clear()


def _resident_signin_redirect():
    return redirect(url_for("resident_requests.resident_signin", next=request.path))


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _safe_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None

    return parsed


def _safe_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None

    return parsed


def _normalized_category_row(row: dict[str, Any]) -> dict[str, Any] | None:
    item = dict(row)
    label = _clean_text(item.get("activity_label"))
    if not label:
        return None

    key = _clean_text(item.get("activity_key"))
    normalized_label = label.lower()

    legacy_parent_key = LEGACY_ACTIVITY_LABEL_TO_PARENT_ACTIVITY_KEY.get(normalized_label, "")
    if legacy_parent_key:
        item["activity_key"] = legacy_parent_key
        item["activity_label"] = LOCKED_PARENT_ACTIVITY_DEFINITIONS.get(legacy_parent_key, label)
        return item

    if key in LOCKED_PARENT_ACTIVITY_DEFINITIONS:
        item["activity_label"] = LOCKED_PARENT_ACTIVITY_DEFINITIONS[key]
        return item

    for k, v in LOCKED_PARENT_ACTIVITY_DEFINITIONS.items():
        if normalized_label == v.lower():
            item["activity_key"] = k
            item["activity_label"] = v
            return item

    return item


def _daily_log_event_time_iso(log_date_text: str) -> str | None:
    try:
        parsed_date = datetime.strptime(log_date_text, "%Y-%m-%d")
    except ValueError:
        return None

    local_dt = parsed_date.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=CHICAGO_TZ)
    utc_dt = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
    return utc_dt.isoformat(timespec="seconds")


def _load_resident_program_level(resident_id: int | None) -> int:
    if resident_id is None:
        return 0

    row = db_fetchone(
        _sql(
            """
            SELECT program_level
            FROM residents
            WHERE id = %s
            LIMIT 1
            """,
            """
            SELECT program_level
            FROM residents
            WHERE id = ?
            LIMIT 1
            """,
        ),
        (resident_id,),
    )

    if not row:
        return 0

    return _safe_int(row.get("program_level")) or 0


def _load_daily_log_categories(shelter: str) -> list[dict[str, Any]]:
    if not shelter:
        return []

    rows = load_kiosk_activity_categories_for_shelter(shelter)
    categories: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows or []:
        item = _normalized_category_row(row)
        if not item:
            continue

        label = _clean_text(item.get("activity_label"))
        if not label or not item.get("active"):
            continue

        token = _clean_text(item.get("activity_key")).lower() or label.lower()
        if token in seen:
            continue
        seen.add(token)

        categories.append(item)

    return categories


def _load_child_options_by_parent(shelter: str, checkout_categories: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    if not shelter:
        return {}

    parent_keys = {
        _clean_text(item.get("activity_key"))
        for item in checkout_categories
        if _clean_text(item.get("activity_key"))
    }

    child_options_by_parent: dict[str, list[dict[str, Any]]] = {}
    for parent_key in sorted(parent_keys):
        rows = load_active_kiosk_activity_child_options_for_shelter(shelter, parent_key)
        options: list[dict[str, Any]] = []

        for row in rows or []:
            item = dict(row)
            if not _clean_text(item.get("option_label")):
                continue
            options.append(item)

        if options:
            child_options_by_parent[parent_key] = options

    return child_options_by_parent

# rest of file unchanged...
