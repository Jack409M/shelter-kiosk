from __future__ import annotations

from core.db import db_execute, db_fetchone
from core.runtime import init_db


TEST_TIMESTAMP = "2026-01-01T00:00:00"


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _insert_resident(app):
    with app.app_context():
        init_db()
        db_execute("DELETE FROM residents")
        db_execute(
            """
            INSERT INTO residents (shelter, resident_identifier, resident_code, first_name, last_name, program_level, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            ("abba", "R1", "12345678", "Test", "User", "5", True, TEST_TIMESTAMP),
        )
        row = db_fetchone("SELECT id FROM residents LIMIT 1")
        return int(row["id"])


def test_resident_daily_log_hours_submission(app, client, monkeypatch):
    resident_id = _insert_resident(app)

    import routes.resident_portal as rp

    monkeypatch.setattr(
        rp,
        "load_kiosk_activity_categories_for_shelter",
        lambda shelter: [
            {"activity_label": "Work", "activity_key": "work", "active": True}
        ],
    )
    monkeypatch.setattr(rp, "load_active_kiosk_activity_child_options_for_shelter", lambda *args, **kwargs: [])

    with client.session_transaction() as session:
        session["resident_id"] = resident_id
        session["resident_identifier"] = "R1"
        session["resident_first"] = "Test"
        session["resident_last"] = "User"
        session["resident_shelter"] = "abba"

    csrf = _set_csrf_token(client)

    response = client.post(
        "/resident/daily-log",
        data={
            "_csrf_token": csrf,
            "log_date": "2026-04-15",
            "activity_category": "Work",
            "hours": "4",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        row = db_fetchone("SELECT * FROM attendance_events LIMIT 1")
        assert row is not None
        assert row["event_type"] == "resident_daily_log"
        assert row["destination"] == "Work"
        assert float(row["logged_hours"]) == 4.0
