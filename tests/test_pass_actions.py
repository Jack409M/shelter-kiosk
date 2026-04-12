from __future__ import annotations

from core.runtime import init_db


def _login_staff(client):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = "case_manager"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba", "haven", "gratitude"]


def _set_csrf(client):
    with client.session_transaction() as session:
        session["_csrf_token"] = "test"
    return "test"


# -----------------------------------------
# APPROVE PASS
# -----------------------------------------

def test_approve_pass_updates_all_fields(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)
    csrf = _set_csrf(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM resident_passes WHERE id = 999")

        db_execute("""
            INSERT INTO residents (id, first_name, last_name, shelter)
            VALUES (1, 'Test', 'User', 'abba')
        """)

        db_execute("""
            INSERT INTO resident_passes (
                id, resident_id, shelter, status, pass_type
            )
            VALUES (999, 1, 'abba', 'pending', 'pass')
        """)

        db_execute("""
            INSERT INTO resident_pass_request_details (pass_id)
            VALUES (999)
        """)

    client.get("/staff/passes/pending")

    client.get(f"/staff/passes/approve/999", follow_redirects=False)

    with app.app_context():
        row = db_fetchone(
            "SELECT status, approved_by, approved_at FROM resident_passes WHERE id = 999"
        )

        assert row["status"] == "approved"
        assert row["approved_by"] is not None
        assert row["approved_at"] is not None


# -----------------------------------------
# DENY PASS
# -----------------------------------------

def test_deny_pass_sets_denied(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM resident_passes WHERE id = 998")

        db_execute("""
            INSERT INTO residents (id, first_name, last_name, shelter)
            VALUES (2, 'Deny', 'User', 'abba')
        """)

        db_execute("""
            INSERT INTO resident_passes (
                id, resident_id, shelter, status, pass_type
            )
            VALUES (998, 2, 'abba', 'pending', 'pass')
        """)

        db_execute("""
            INSERT INTO resident_pass_request_details (pass_id)
            VALUES (998)
        """)

    client.get(f"/staff/passes/deny/998", follow_redirects=False)

    with app.app_context():
        row = db_fetchone(
            "SELECT status FROM resident_passes WHERE id = 998"
        )

        assert row["status"] == "denied"


# -----------------------------------------
# CHECK IN PASS
# -----------------------------------------

def test_check_in_creates_attendance_event(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM resident_passes WHERE id = 997")

        db_execute("""
            INSERT INTO residents (id, first_name, last_name, shelter)
            VALUES (3, 'Return', 'User', 'abba')
        """)

        db_execute("""
            INSERT INTO resident_passes (
                id, resident_id, shelter, status, pass_type
            )
            VALUES (997, 3, 'abba', 'approved', 'pass')
        """)

    client.get(f"/staff/passes/check-in/997", follow_redirects=False)

    with app.app_context():
        row = db_fetchone(
            "SELECT COUNT(*) as count FROM attendance_events WHERE resident_id = 3"
        )

        assert row["count"] == 1


# -----------------------------------------
# SMS FAILURE DOES NOT BREAK APPROVAL
# -----------------------------------------

def test_sms_failure_does_not_break_approval(app, client, monkeypatch):
    from core.db import db_execute, db_fetchone

    _login_staff(client)

    def fail_sms(*args, **kwargs):
        raise Exception("sms failure")

    monkeypatch.setattr("core.sms_sender.send_sms", fail_sms)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM resident_passes WHERE id = 996")

        db_execute("""
            INSERT INTO residents (id, first_name, last_name, shelter)
            VALUES (4, 'SMS', 'Fail', 'abba')
        """)

        db_execute("""
            INSERT INTO resident_passes (
                id, resident_id, shelter, status, pass_type
            )
            VALUES (996, 4, 'abba', 'pending', 'pass')
        """)

        db_execute("""
            INSERT INTO resident_pass_request_details (pass_id)
            VALUES (996)
        """)

    client.get(f"/staff/passes/approve/996", follow_redirects=False)

    with app.app_context():
        row = db_fetchone(
            "SELECT status FROM resident_passes WHERE id = 996"
        )

        assert row["status"] == "approved"
