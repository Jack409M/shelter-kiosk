from core.db import db_fetchall


def audit_events_for_resident(resident_id: int):
    return db_fetchall(
        """
        SELECT
            created_at AS event_time,
            action_type AS event_type,
            action_type AS title,
            action_details AS detail,
            100 AS sort_order
        FROM audit_log
        WHERE entity_type = 'resident'
        AND entity_id = ?
        ORDER BY created_at DESC
        """,
        (resident_id,),
    )
