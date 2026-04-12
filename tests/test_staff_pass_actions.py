from __future__ import annotations

from core.runtime import init_db


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _login_staff(client, role: str = "case_manager") -> None:
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = role
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]


def _insert_resident(app, *, resident_identifier: str, resident_code: str) -> int:
    from core.db import db_execute, db_fetchone

    with app.app_context():
        init_db()

        db_execute(
            """
            DELETE FROM resident_notifications
            WHERE resident_id IN (
                SELECT id FROM residents WHERE resident_identifier = %s
            )
            """,
            (resident_identifier,),
        )
        db_execute(
            """
            DELETE FROM resident_pass_request_details
            WHERE pass_id IN (
                SELECT rp.id
                FROM resident_passes rp
                JOIN residents r ON r.id = rp.resident_id
                WHERE r.resident_identifier = %s
            )
            """,
            (resident_identifier,),
        )
        db_execute(
            """
            DELETE FROM attendance_events
            WHERE resident_id IN (
                SELECT id FROM residents WHERE resident_identifier = %s
            )
            """,
            (resident_identifier,),
        )
        db_execute(
            """
            DELETE FROM resident_passes
            WHERE resident_id IN (
                SELECT id FROM residents WHERE resident_identifier = %s
            )
            """,
            (resident_identifier,),
        )
        db_execute(
            """
            DELETE FROM residents
            WHERE resident_identifier = %s
               OR resident_code = %s
            """,
            (resident_identifier, resident_code),
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
                resident_identifier,
                resident_code,
                "Jane",
                "Resident",
                "abba",
                True,
                "2026-01-01T00:00:00",
            ),
        )

        row = db_fetchone(
            """
            SELECT id
            FROM residents
            WHERE resident_identifier = %s
            """,
            (resident_identifier,),
        )
        return int(row["id"])


def _insert_pass(app, *, resident_id: int, status: str) -> int:
    from core.db import db_execute, db_fetchone

    with app.app_context():
        init_db()

        db_execute(
            """
            INSERT INTO resident_passes (
                resident_id,
                shelter,
                pass_type,
                status,
                start_at,
                end_at,
                destination,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resident_id,
                "abba",
                "pass",
                status,
                "2099-01-01T10:00:00",
                "2099-01-01T18:00:00",
                "Clinic",
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )

        row = db_fetchone(
            """
            SELECT id
            FROM resident_passes
            WHERE resident_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (resident_id,),
        )
        pass_id = int(row["id"])

        db_execute(
            """
            INSERT INTO resident_pass_request_details (
                pass_id,
                resident_phone,
                reviewed_by_user_id,
                reviewed_by_name,
                reviewed_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                pass_id,
                "5551112222",
                None,
                None,
                None,
                "2026-01-01T00:00:00",
            ),
        )

        return pass_id


def test_staff_pass_approve_updates_db_and_creates_notification(app, client, monkeypatch):
    from core.db import db_fetchone
    import routes.attendance_parts.pass_actions as actions_module

    _login_staff(client)
    csrf_token = _set_csrf_token(client)

    resident_id = _insert_resident(
        app,
        resident_identifier="test_pass_approve_resident",
        resident_code="91000001",
    )
    pass_id = _insert_pass(app, resident_id=resident_id, status="pending")

    monkeypatch.setattr(actions_module, "send_sms", lambda *args, **kwargs: None)
    monkeypatch.setattr(actions_module, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        f"/staff/passes/{pass_id}/approve",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/passes/pending" in response.headers["Location"]

    with app.app_context():
        pass_row = db_fetchone(
            """
            SELECT status, approved_by, approved_at, delete_after_at
            FROM resident_passes
            WHERE id = %s
            """,
            (pass_id,),
        )
        detail_row = db_fetchone(
            """
            SELECT reviewed_by_user_id, reviewed_by_name, reviewed_at
            FROM resident_pass_request_details
            WHERE pass_id = %s
            """,
            (pass_id,),
        )
        notification_row = db_fetchone(
            """
            SELECT notification_type, title, message, related_pass_id
            FROM resident_notifications
            WHERE resident_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (resident_id,),
        )

    assert pass_row["status"] == "approved"
    assert pass_row["approved_by"] == 1
    assert pass_row["approved_at"]
    assert pass_row["delete_after_at"]

    assert detail_row["reviewed_by_user_id"] == 1
    assert detail_row["reviewed_by_name"] == "staff"
    assert detail_row["reviewed_at"]

    assert notification_row["notification_type"] == "pass_approved"
    assert notification_row["related_pass_id"] == pass_id
    assert "approved" in notification_row["message"].lower()


def test_staff_pass_deny_updates_db_and_creates_notification(app, client, monkeypatch):
    from core.db import db_fetchone
    import routes.attendance_parts.pass_actions as actions_module

    _login_staff(client)
    csrf_token = _set_csrf_token(client)

    resident_id = _insert_resident(
        app,
        resident_identifier="test_pass_deny_resident",
        resident_code="91000002",
    )
    pass_id = _insert_pass(app, resident_id=resident_id, status="pending")

    monkeypatch.setattr(actions_module, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        f"/staff/passes/{pass_id}/deny",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/passes/pending" in response.headers["Location"]

    with app.app_context():
        pass_row = db_fetchone(
            """
            SELECT status, approved_by, approved_at
            FROM resident_passes
            WHERE id = %s
            """,
            (pass_id,),
        )
        detail_row = db_fetchone(
            """
            SELECT reviewed_by_user_id, reviewed_by_name, reviewed_at
            FROM resident_pass_request_details
            WHERE pass_id = %s
            """,
            (pass_id,),
        )
        notification_row = db_fetchone(
            """
            SELECT notification_type, title, message, related_pass_id
            FROM resident_notifications
            WHERE resident_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (resident_id,),
        )

    assert pass_row["status"] == "denied"
    assert pass_row["approved_by"] == 1
    assert pass_row["approved_at"]

    assert detail_row["reviewed_by_user_id"] == 1
    assert detail_row["reviewed_by_name"] == "staff"
    assert detail_row["reviewed_at"]

    assert notification_row["notification_type"] == "pass_denied"
    assert notification_row["related_pass_id"] == pass_id
    assert "denied" in notification_row["message"].lower()


def test_staff_pass_check_in_creates_attendance_event_and_completes_pass(app, client, monkeypatch):
    from core.db import db_fetchone
    import routes.attendance_parts.pass_actions as actions_module

    _login_staff(client)
    csrf_token = _set_csrf_token(client)

    resident_id = _insert_resident(
        app,
        resident_identifier="test_pass_checkin_resident",
        resident_code="91000003",
    )
    pass_id = _insert_pass(app, resident_id=resident_id, status="approved")

    monkeypatch.setattr(actions_module, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        f"/staff/passes/{pass_id}/check-in",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/passes/away-now" in response.headers["Location"]

    with app.app_context():
        pass_row = db_fetchone(
            """
            SELECT status, delete_after_at
            FROM resident_passes
            WHERE id = %s
            """,
            (pass_id,),
        )
        attendance_row = db_fetchone(
            """
            SELECT event_type, staff_user_id, note
            FROM attendance_events
            WHERE resident_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (resident_id,),
        )

    assert pass_row["status"] == "completed"
    assert pass_row["delete_after_at"]

    assert attendance_row["event_type"] == "check_in"
    assert attendance_row["staff_user_id"] == 1
    assert "pass return" in attendance_row["note"].lower()


def test_staff_pass_actions_forbid_non_manager_role(app, client):
    resident_id = _insert_resident(
        app,
        resident_identifier="test_pass_forbidden_resident",
        resident_code="91000004",
    )
    pass_id = _insert_pass(app, resident_id=resident_id, status="pending")

    _login_staff(client, role="staff")
    csrf_token = _set_csrf_token(client)

    response = client.post(
        f"/staff/passes/{pass_id}/approve",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 403
