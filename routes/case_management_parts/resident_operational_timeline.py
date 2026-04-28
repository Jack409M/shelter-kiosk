from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from flask import flash, redirect, render_template, session, url_for

from core.db import db_fetchall
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    placeholder,
)
from routes.case_management_parts.resident_case_scope import load_resident_in_scope

CHICAGO_TZ = ZoneInfo("America/Chicago")

ACTION_LABELS = {
    "approve": "Approved",
    "check_in": "Checked In",
    "create": "Created",
    "create_existing_resident": "Intake Created for Existing Resident",
    "delete": "Deleted",
    "deny": "Denied",
    "exit": "Exit Completed",
    "profile_update": "Profile Updated",
    "resident_deactivated_from_placement_board": "Resident Deactivated from Placement Board",
    "security_setting_updated": "Security Setting Updated",
    "submit": "Submitted",
    "transfer": "Transfer Completed",
    "update": "Updated",
}

ENTITY_LABELS = {
    "case_note": "Case Note",
    "enrollment": "Enrollment",
    "intake": "Intake",
    "placement": "Placement",
    "rent": "Rent",
    "resident": "Resident",
    "resident_pass": "Pass",
}

EXCLUDED_ENTITY_TYPES = {"auth", "security", "security_settings"}


def _require_case_manager_access():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))
    return None


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _format_chicago_time(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        local_dt = parsed.astimezone(CHICAGO_TZ)
        return local_dt.strftime("%m/%d/%Y %I:%M %p")
    except Exception:
        return raw


def _title_from_key(value: object) -> str:
    key = str(value or "").strip().lower()
    if not key:
        return "Action"
    return ACTION_LABELS.get(key, key.replace("_", " ").title())


def _entity_label(value: object) -> str:
    key = str(value or "").strip().lower()
    if not key:
        return "Record"
    return ENTITY_LABELS.get(key, key.replace("_", " ").title())


def _format_details(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    parts = []
    for item in raw.split():
        if "=" not in item:
            parts.append(item)
            continue

        key, detail_value = item.split("=", 1)
        if key in {"ip", "username"}:
            continue
        label = key.replace("_", " ").title()
        parts.append(f"{label}: {detail_value}")

    return " | ".join(parts)


def _load_operational_timeline_entries(resident_id: int) -> list[dict]:
    ph = placeholder()
    rows = db_fetchall(
        f"""
        SELECT
            a.id,
            a.entity_type,
            a.entity_id,
            a.action_type,
            a.action_details,
            a.created_at,
            a.staff_user_id,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        WHERE (
                a.entity_type = 'resident'
                AND a.entity_id = {ph}
              )
           OR a.action_details LIKE {ph}
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT 200
        """,
        (resident_id, f"%resident_id={resident_id}%"),
    )

    entries = []
    seen_ids = set()

    for row in rows or []:
        item = dict(row)
        entry_id = item.get("id")
        entity_type = str(item.get("entity_type") or "").strip().lower()

        if entry_id in seen_ids or entity_type in EXCLUDED_ENTITY_TYPES:
            continue

        seen_ids.add(entry_id)
        entries.append(
            {
                "id": entry_id,
                "time_display": _format_chicago_time(item.get("created_at")),
                "action_display": _title_from_key(item.get("action_type")),
                "entity_display": _entity_label(entity_type),
                "details_display": _format_details(item.get("action_details")),
                "staff_display": item.get("staff_username") or "System",
            }
        )

    return entries


def resident_operational_timeline_view(resident_id: int):
    denied = _require_case_manager_access()
    if denied is not None:
        return denied

    init_db()

    shelter = _current_shelter()
    resident = load_resident_in_scope(resident_id, shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    entries = _load_operational_timeline_entries(resident_id)

    return render_template(
        "case_management/resident_operational_timeline.html",
        resident=resident,
        entries=entries,
    )
