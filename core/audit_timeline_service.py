from __future__ import annotations

from core.db import db_fetchall


def get_resident_audit_timeline(resident_id: int) -> list[dict]:
    return db_fetchall(
        """
        SELECT
            'field_change' AS event_type,
            field_name AS event_name,
            old_value AS old_value,
            new_value AS new_value,
            change_reason AS detail,
            created_at AS created_at,
            changed_by_user_id AS staff_user_id
        FROM field_change_audit
        WHERE entity_type = %s
          AND entity_id = %s

        UNION ALL

        SELECT
            'action' AS event_type,
            action_type AS event_name,
            '' AS old_value,
            action_details AS new_value,
            action_details AS detail,
            created_at AS created_at,
            staff_user_id AS staff_user_id
        FROM audit_log
        WHERE entity_type = %s
          AND entity_id = %s

        ORDER BY created_at DESC
        """,
        ("resident", resident_id, "resident", resident_id),
    )
