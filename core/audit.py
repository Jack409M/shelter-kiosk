from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask import current_app

from core.db import db_execute
from core.helpers import utcnow_iso


def _normalize_detail_value(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, bool):
        return "1" if value else "0"

    return str(value).strip()


def _normalize_details(details: str | Mapping[str, Any] | None) -> str:
    if details is None:
        return ""

    if isinstance(details, str):
        return details.strip()

    parts: list[str] = []

    for key in sorted(details.keys()):
        raw_value = _normalize_detail_value(details.get(key))
        if raw_value == "":
            continue

        safe_key = str(key).strip().lower().replace(" ", "_")
        safe_value = raw_value.replace("\n", " ").strip()
        parts.append(f"{safe_key}={safe_value}")

    return " ".join(parts)


def log_action(
    entity_type: str,
    entity_id: int | None,
    shelter: str | None,
    staff_user_id: int | None,
    action_type: str,
    details: str | Mapping[str, Any] | None = "",
) -> None:
    normalized_entity_type = (entity_type or "").strip().lower()
    normalized_action_type = (action_type or "").strip().lower()
    normalized_shelter = (shelter or "").strip() or None
    normalized_details = _normalize_details(details)

    sql = (
        "INSERT INTO audit_log (entity_type, entity_id, shelter, staff_user_id, action_type, action_details, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if current_app.config.get("DATABASE_URL")
        else "INSERT INTO audit_log (entity_type, entity_id, shelter, staff_user_id, action_type, action_details, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    db_execute(
        sql,
        (
            normalized_entity_type,
            entity_id,
            normalized_shelter,
            staff_user_id,
            normalized_action_type,
            normalized_details,
            utcnow_iso(),
        ),
    )
