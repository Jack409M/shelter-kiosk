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
    _set_csrf(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM resident_pass_request_details WHERE pass_id = 999")
        db_execute("DELETE FROM resident_notifications WHERE related_pass_id = 999")
        db_execute("DELETE FROM resident_passes WHERE id = 999")
        db_execute("DELETE FROM residents WHERE id = 1")

        db_execute(
            """
            INSERT INTO residents (id, first_name, last_name, shelter)
            VALUES (1, 'Test', 'User', 'abba')
            """
        )

        db_execute(
            """
            INSERT INTO resident_passes (
                id, resident_id, shelter, status, pass_type, created_at, updated_at
            )
            VALUES (999, 1, 'abba', 'pending', 'pass', '2026-01-01', '2026-01-01')
            """
        )

        db_execute(
            """
            INSERT INTO resident_pass_request_details (pass_id, created_at, updated_at)
            VALUES (999, '2026-01-01', '2026-01-01')
            """
        )

    client.get("/staff/passes/pending")
    client.get("/staff/passes/approve/999", follow_redirects=False)

    with app.app_context():
        row = db_fetchone(
            "SELECT status, approved_by, approved_at FROM resident_passes WHERE id = 999"
        )
        audit = db_fetchone(
            """
            SELECT entity_type, action_type, action_details
            FROM audit_log
            WHERE entity_type = 'pass'
              AND action_type = 'approve'
            ORDER BY id DESC
            LIMIT 1
            """
        )

        assert row["status"] == "approved"
        assert row["approved_by"] is not None
        assert row["approved_at"] is not None

        assert audit is not None
        assert audit["entity_type"] == "pass"
        assert audit["action_type"] == "approve"
        assert "pass_id=999" in str(audit["action_details"] or "")


def test_approve_pass_requires_login(client):
    response = client.get("/staff/passes/approve/995", follow_redirects=False)

    assert response.status_code == 302
    assert "/staff/login" in response.headers["Location"]


def test_approve_pass_with_shelter_mismatch_does_not_approve(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)
    _set_csrf(client)

    with client.session_transaction() as session:
        session["shelter"] = "haven"
        session["allowed_shelters"] = ["haven"]

    with app.app_context():
        init_db()

        db_execute("DELETE FROM resident_pass_request_details WHERE pass_id = 995")
        db_execute("DELETE FROM resident_notifications WHERE related_pass_id = 995")
        db_execute("DELETE FROM resident_passes WHERE id = 995")
        db_execute("DELETE FROM residents WHERE id = 5")

        db_execute(
            """
            INSERT INTO residents (id, first_name, last_name, shelter)
            VALUES (5, 'Wrong', 'Shelter', 'abba')
            """
        )

        db_execute(
            """
            INSERT INTO resident_passes (
                id, resident_id, shelter, status, pass_type, created_at, updated_at
            )
            VALUES (995, 5, 'abba', 'pending', 'pass', '2026-01-01', '2026-01-01')
            """
        )

        db_execute(
            """
            INSERT INTO resident_pass_request_details (pass_id, created_at, updated_at)
            VALUES (995, '2026-01-01', '2026-01-01')
            """
        )

    client.get("/staff/passes/approve/995", follow_redirects=False)

    with app.app_context():
        row = db_fetchone("SELECT status FROM resident_passes WHERE id = 995")

        assert row["status"] == "pending"


def test_approve_nonexistent_pass_is_safe(app, client):
    from core.db import db_fetchone

    _login_staff(client)
    _set_csrf(client)

    with app.app_context():
        init_db()

    response = client.get("/staff/passes/approve/123456", follow_redirects=False)

    assert response.status_code in (200, 302, 404)

    with app.app_context():
        audit = db_fetchone(
            """
            SELECT entity_type, action_type, action_details
            FROM audit_log
            WHERE entity_type = 'pass'
              AND action_type = 'approve'
              AND action_details LIKE '%123456%'
            ORDER BY id DESC
            LIMIT 1
            """
        )

        assert audit is None


# -----------------------------------------
# DENY PASS
# -----------------------------------------
def test_deny_pass_sets_denied(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM resident_pass_request_details WHERE pass_id = 998")
        db_execute("DELETE FROM resident_notifications WHERE related_pass_id = 998")
        db_execute("DELETE FROM resident_passes WHERE id = 998")
        db_execute("DELETE FROM residents WHERE id = 2")

        db_execute(
            """
            INSERT INTO residents (id, first_name, last_name, shelter)
            VALUES (2, 'Deny', 'User', 'abba')
            """
        )

        db_execute(
            """
            INSERT INTO resident_passes (
                id, resident_id, shelter, status, pass_type, created_at, updated_at
            )
            VALUES (998, 2, 'abba', 'pending', 'pass', '2026-01-01', '2026-01-01')
            """
        )

        db_execute(
            """
            INSERT INTO resident_pass_request_details (pass_id, created_at, updated_at)
            VALUES (998, '2026-01-01', '2026-01-01')
            """
        )

    client.get("/staff/passes/deny/998", follow_redirects=False)

    with app.app_context():
        row = db_fetchone("SELECT status FROM resident_passes WHERE id = 998")
        audit = db_fetchone(
            """
            SELECT entity_type, action_type, action_details
            FROM audit_log
            WHERE entity_type = 'pass'
              AND action_type = 'deny'
            ORDER BY id DESC
            LIMIT 1
            """
        )

        assert row["status"] == "denied"

        assert audit is not None
        assert audit["entity_type"] == "pass"
        assert audit["action_type"] == "deny"
        assert "pass_id=998" in str(audit["action_details"] or "")


def test_deny_pass_requires_login(client):
    response = client.get("/staff/passes/deny/994", follow_redirects=False)

    assert response.status_code == 302
    assert "/staff/login" in response.headers["Location"]


def test_deny_pass_with_shelter_mismatch_does_not_deny(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)

    with client.session_transaction() as session:
        session["shelter"] = "haven"
        session["allowed_shelters"] = ["haven"]

    with app.app_context():
        init_db()

        db_execute("DELETE FROM resident_pass_request_details WHERE pass_id = 994")
        db_execute("DELETE FROM resident_notifications WHERE related_pass_id = 994")
        db_execute("DELETE FROM resident_passes WHERE id = 994")
        db_execute("DELETE FROM residents WHERE id = 6")

        db_execute(
            """
            INSERT INTO residents (id, first_name, last_name, shelter)
            VALUES (6, 'Wrong', 'Shelter', 'abba')
            """
        )

        db_execute(
            """
            INSERT INTO resident_passes (
                id, resident_id, shelter, status, pass_type, created_at, updated_at
            )
            VALUES (994, 6, 'abba', 'pending', 'pass', '2026-01-01', '2026-01-01')
            """
        )

        db_execute(
            """
            INSERT INTO resident_pass_request_details (pass_id, created_at, updated_at)
            VALUES (994, '2026-01-01', '2026-01-01')
            """
        )

    client.get("/staff/passes/deny/994", follow_redirects=False)

    with app.app_context():
        row = db_fetchone("SELECT status FROM resident_passes WHERE id = 994")

        assert row["status"] == "pending"


def test_deny_nonexistent_pass_is_safe(app, client):
    from core.db import db_fetchone

    _login_staff(client)

    with app.app_context():
        init_db()

    response = client.get("/staff/passes/deny/123457", follow_redirects=False)

    assert response.status_code in (200, 302, 404)

    with app.app_context():
        audit = db_fetchone(
            """
            SELECT entity_type, action_type, action_details
            FROM audit_log
            WHERE entity_type = 'pass'
              AND action_type = 'deny'
              AND action_details LIKE '%123457%'
            ORDER BY id DESC
            LIMIT 1
            """
        )

        assert audit is None


# -----------------------------------------
# CHECK IN PASS
# -----------------------------------------
def test_check_in_creates_attendance_event(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM resident_passes WHERE id = 997")
        db_execute("DELETE FROM residents WHERE id = 3")
        db_execute("DELETE FROM attendance_events WHERE resident_id = 3")

        db_execute(
            """
            INSERT INTO residents (id, first_name, last_name, shelter)
            VALUES (3, 'Return', 'User', 'abba')
            """
        )

        db_execute(
            """
            INSERT INTO resident_passes (
                id, resident_id, shelter, status, pass_type, created_at, updated_at
            )
            VALUES (997, 3, 'abba', 'approved', 'pass', '2026-01-01', '2026-01-01')
            """
        )

    client.get("/staff/passes/check-in/997", follow_redirects=False)

    with app.app_context():
        row = db_fetchone(
            "SELECT COUNT(*) as count FROM attendance_events WHERE resident_id = 3"
        )
        audit = db_fetchone(
            """
            SELECT entity_type, action_type, action_details
            FROM audit_log
            WHERE entity_type = 'pass'
              AND action_type = 'check_in'
            ORDER BY id DESC
            LIMIT 1
            """
        )

        assert row["count"] == 1

        assert audit is not None
        assert audit["entity_type"] == "pass"
        assert audit["action_type"] == "check_in"
        assert "pass_id=997" in str(audit["action_details"] or "")


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

        db_execute("DELETE FROM resident_pass_request_details WHERE pass_id = 996")
        db_execute("DELETE FROM resident_notifications WHERE related_pass_id = 996")
        db_execute("DELETE FROM resident_passes WHERE id = 996")
        db_execute("DELETE FROM residents WHERE id = 4")

        db_execute(
            """
            INSERT INTO residents (id, first_name, last_name, shelter)
            VALUES (4, 'SMS', 'Fail', 'abba')
            """
        )

        db_execute(
            """
            INSERT INTO resident_passes (
                id, resident_id, shelter, status, pass_type, created_at, updated_at
            )
            VALUES (996, 4, 'abba', 'pending', 'pass', '2026-01-01', '2026-01-01')
            """
        )

        db_execute(
            """
            INSERT INTO resident_pass_request_details (pass_id, created_at, updated_at)
            VALUES (996, '2026-01-01', '2026-01-01')
            """
        )

    client.get("/staff/passes/approve/996", follow_redirects=False)

    with app.app_context():
        row = db_fetchone("SELECT status FROM resident_passes WHERE id = 996")
        audit = db_fetchone(
            """
            SELECT entity_type, action_type, action_details
            FROM audit_log
            WHERE entity_type = 'pass'
              AND action_type = 'approve'
            ORDER BY id DESC
            LIMIT 1
            """
        )

        assert row["status"] == "approved"

        assert audit is not None
        assert audit["entity_type"] == "pass"
        assert audit["action_type"] == "approve"
        assert "pass_id=996" in str(audit["action_details"] or "")
