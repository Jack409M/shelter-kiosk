from __future__ import annotations

from typing import Any

from core.db import db_execute
from core.helpers import utcnow_iso


def _normalize_audit_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value).strip()


def log_field_change(
    *,
    entity_type: str,
    entity_id: int | None,
    table_name: str,
    field_name: str,
    old_value: Any,
    new_value: Any,
    changed_by_user_id: int | None,
    shelter: str | None,
    change_reason: str = "",
) -> None:
    old_text = _normalize_audit_value(old_value)
    new_text = _normalize_audit_value(new_value)

    if old_text == new_text:
        return

    db_execute(
        """
        INSERT INTO field_change_audit (
            entity_type,
            entity_id,
            table_name,
            field_name,
            old_value,
            new_value,
            changed_by_user_id,
            shelter,
            change_reason,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(entity_type or "").strip().lower(),
            entity_id,
            str(table_name or "").strip().lower(),
            str(field_name or "").strip().lower(),
            old_text,
            new_text,
            changed_by_user_id,
            str(shelter or "").strip().lower() or None,
            str(change_reason or "").strip(),
            utcnow_iso(),
        ),
    )
