from __future__ import annotations

from datetime import datetime, timedelta

from core.runtime import init_db


def _insert_resident(app, *, identifier: str) -> int:
    from core.db import db_execute, db_fetchone

    with app.app_context():
        init_db()

        db_execute(
            """
            DELETE FROM residents WHERE resident_identifier = %s
            """,
            (identifier,),
        )

        db_execute(
            """
            INSERT INTO residents (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                identifier,
                "99999999",
                "Test",
                "Resident",
                "abba",
                True,
                "2026-01-01T00:00:00",
            ),
        )

        row = db_fetchone(
            "SELECT id FROM residents WHERE resident_identifier = %s",
            (identifier,),
        )

        return int(row["id"])


def _insert_pass(app, *, resident_id: int, delete_after_at: str | None):
    from core.db import db_execute

    with app.app_context():
        db_execute(
            """
            INSERT INTO resident_passes (
                resident_id,
                shelter,
                pass_type,
                status,
                start_at,
                end_at,
                delete_after_at,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resident_id,
                "abba",
                "pass",
                "approved",
                "2026-01-01T10:00:00",
                "2026-01-01T18:00:00",
                delete_after_at,
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )


def test_pass_retention_deletes_expired_passes(app):
    from core.db import db_fetchall
    from core.pass_retention import run_pass_retention_cleanup_for_shelter

    resident_id = _insert_resident(app, identifier="retention_delete_test")

    past_time = (datetime.utcnow() - timedelta(days=2)).isoformat()

    _insert_pass(app, resident_id=resident_id, delete_after_at=past_time)

    result = run_pass_retention_cleanup_for_shelter("abba")

    assert result["deleted"] >= 1

    with app.app_context():
        rows = db_fetchall(
            "SELECT * FROM resident_passes WHERE resident_id = %s",
            (resident_id,),
        )

    assert len(rows) == 0


def test_pass_retention_backfills_missing_delete_after(app):
    from core.db import db_fetchone
    from core.pass_retention import run_pass_retention_cleanup_for_shelter

    resident_id = _insert_resident(app, identifier="retention_backfill_test")

    _insert_pass(app, resident_id=resident_id, delete_after_at=None)

    result = run_pass_retention_cleanup_for_shelter("abba")

    assert result["backfilled"] >= 1

    with app.app_context():
        row = db_fetchone(
            "SELECT delete_after_at FROM resident_passes WHERE resident_id = %s",
            (resident_id,),
        )

    assert row["delete_after_at"] is not None
