from __future__ import annotations

from core.runtime import init_db


def _row_value(row, key: str, index: int):
    if isinstance(row, dict):
        return row[key]
    return row[index]


def test_audit_log_table_exists_and_accepts_writes(app):
    from core.audit import log_action
    from core.db import db_fetchall

    with app.app_context():
        init_db()

        log_action(
            entity_type="resident",
            entity_id=1,
            shelter="abba",
            staff_user_id=99,
            action_type="test_event",
            details="smoke test",
        )

        rows = db_fetchall(
            """
            SELECT entity_type, entity_id, shelter, staff_user_id, action_type, action_details
            FROM audit_log
            WHERE entity_type = 'resident'
              AND entity_id = 1
              AND action_type = 'test_event'
            ORDER BY id DESC
            """
        )

    assert rows

    row = rows[0]

    assert _row_value(row, "entity_type", 0) == "resident"
    assert _row_value(row, "entity_id", 1) == 1
    assert _row_value(row, "shelter", 2) == "abba"
    assert _row_value(row, "staff_user_id", 3) == 99
    assert _row_value(row, "action_type", 4) == "test_event"
    assert _row_value(row, "action_details", 5) == "smoke test"
