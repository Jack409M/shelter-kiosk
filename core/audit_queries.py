from __future__ import annotations

from core.db import db_fetchall


def audit_events_for_resident(resident_id: int) -> list[dict]:
    return db_fetchall(
        """
        SELECT
            created_at AS event_time,
            'action' AS event_source,
            action_type AS event_type,
            action_type AS title,
            action_details AS detail,
            '' AS old_value,
            action_details AS new_value,
            staff_user_id AS staff_user_id,
            100 AS sort_order
        FROM audit_log
        WHERE entity_type = %s
          AND entity_id = %s

        UNION ALL

        SELECT
            created_at AS event_time,
            'field_change' AS event_source,
            field_name AS event_type,
            field_name AS title,
            change_reason AS detail,
            old_value AS old_value,
            new_value AS new_value,
            changed_by_user_id AS staff_user_id,
            50 AS sort_order
        FROM field_change_audit
        WHERE entity_type = %s
          AND entity_id = %s

        ORDER BY event_time DESC, sort_order ASC
        """,
        ("resident", resident_id, "resident", resident_id),
    )
