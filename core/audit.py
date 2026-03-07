from __future__ import annotations

from typing import Optional

from flask import current_app

from core.db import db_execute
from core.helpers import utcnow_iso


def log_action(
    entity_type: str,
    entity_id: Optional[int],
    shelter: Optional[str],
    staff_user_id: Optional[int],
    action_type: str,
    details: str = "",
) -> None:
    sql = (
        "INSERT INTO audit_log (entity_type, entity_id, shelter, staff_user_id, action_type, action_details, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if current_app.config.get("DATABASE_URL") else
        "INSERT INTO audit_log (entity_type, entity_id, shelter, staff_user_id, action_type, action_details, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    db_execute(
        sql,
        (entity_type, entity_id, shelter, staff_user_id, action_type, details, utcnow_iso()),
    )
