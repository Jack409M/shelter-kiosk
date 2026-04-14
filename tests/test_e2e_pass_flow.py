from __future__ import annotations

from core.runtime import init_db


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _login_resident(
    client,
    *,
    resident_id: int,
    resident_identifier: str,
    first_name: str = "Jane",
    last_name: str = "Resident",
    shelter: str = "abba",
) -> None:
    with client.session_transaction() as session:
        session["resident_id"] = resident_id
        session["resident_identifier"] = resident_identifier
        session["resident_first"] = first_name
        session["resident_last"] = last_name
        session["resident_shelter"] = shelter
        session["sms_consent_done"] = True


def _login_staff(client, *, role: str = "case_manager", shelter: str = "abba") -> None:
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = role
        session["shelter"] = shelter
        session["allowed_shelters"] = [shelter]


def _insert_resident(
    app,
    *,
    resident_identifier: str,
    resident_code: str,
    first_name: str = "Jane",
    last_name: str = "Resident",
    shelter: str = "abba",
    program_level: str = "5",
    phone: str = "5551112222",
) -> int:
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
                program_level,
                phone,
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                shelter,
                program_level,
                phone,
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


def test_full_pass_flow_submit_approve_check_in_and_retention_cleanup(app, client, monkeypatch):
    import routes.attendance_parts.pass_actions as pass_actions_module
    import routes.resident_parts.pass_request as resident_pass_module
    from core.db import db_execute, db_fetchone
    from core.pass_retention import run_pass_retention_cleanup_for_shelter

    resident_id = _insert_resident(
        app,
        resident_identifier="e2e_pass_flow_resident",
        resident_code="88000001",
    )

    monkeypatch.setattr(
        resident_pass_module,
        "calculate_prior_week_attendance_hours",
        lambda resident_id, shelter: None,
    )
    monkeypatch.setattr(resident_pass_module, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(pass_actions_module, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(pass_actions_module, "send_sms", lambda *args, **kwargs: None)

    _login_resident(
        client,
        resident_id=resident_id,
        resident_identifier="e2e_pass_flow_resident",
    )
    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/pass-request",
        data={
            "_csrf_token": csrf_token,
            "pass_type": "pass",
            "destination": "Clinic",
            "reason": "Appointment",
            "resident_notes": "Need to attend appointment",
            "request_date": "2099-01-01",
            "requirements_acknowledged": "yes",
            "resident_phone": "5551112222",
            "start_at": "2099-01-01T10:00",
            "end_at": "2099-01-01T18:00",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)

    with app.app_context():
        pass_row = db_fetchone(
            """
            SELECT id, status, resident_id, shelter, destination
            FROM resident_passes
            WHERE resident_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (resident_id,),
        )
        assert pass_row is not None
        pass_id = int(pass_row["id"])
        assert pass_row["status"] == "pending"
        assert pass_row["shelter"] == "abba"
        assert pass_row["destination"] == "Clinic"

    _login_staff(client, role="case_manager", shelter="abba")
    response = client.get("/staff/passes/pending", follow_redirects=False)

    assert response.status_code == 200
    assert b"Jane" in response.data
    assert b"Resident" in response.data

    csrf_token = _set_csrf_token(client)
    response = client.post(
        f"/staff/passes/{pass_id}/approve",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/passes/pending" in response.headers["Location"]

    with app.app_context():
        approved_row = db_fetchone(
            """
            SELECT status, approved_by, approved_at, delete_after_at
            FROM resident_passes
            WHERE id = %s
            """,
            (pass_id,),
        )
        notification_row = db_fetchone(
            """
            SELECT notification_type, related_pass_id
            FROM resident_notifications
            WHERE resident_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (resident_id,),
        )

    assert approved_row["status"] == "approved"
    assert approved_row["approved_by"] == 1
    assert approved_row["approved_at"]
    assert approved_row["delete_after_at"]
    assert notification_row["notification_type"] == "pass_approved"
    assert notification_row["related_pass_id"] == pass_id

    response = client.get("/staff/passes/approved", follow_redirects=False)

    assert response.status_code == 200
    assert b"Jane" in response.data
    assert b"Resident" in response.data

    csrf_token = _set_csrf_token(client)
    response = client.post(
        f"/staff/passes/{pass_id}/check-in",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/passes/away-now" in response.headers["Location"]

    with app.app_context():
        completed_row = db_fetchone(
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

    assert completed_row["status"] == "completed"
    assert completed_row["delete_after_at"]
    assert attendance_row["event_type"] == "check_in"
    assert attendance_row["staff_user_id"] == 1
    assert "pass return" in str(attendance_row["note"] or "").lower()

    with app.app_context():
        db_execute(
            """
            UPDATE resident_passes
            SET delete_after_at = %s
            WHERE id = %s
            """,
            ("2000-01-01T00:00:00", pass_id),
        )

    with app.app_context():
        result = run_pass_retention_cleanup_for_shelter("abba")

    assert result["deleted"] >= 1

    with app.app_context():
        deleted_row = db_fetchone(
            """
            SELECT id
            FROM resident_passes
            WHERE id = %s
            """,
            (pass_id,),
        )
        deleted_detail = db_fetchone(
            """
            SELECT pass_id
            FROM resident_pass_request_details
            WHERE pass_id = %s
            """,
            (pass_id,),
        )
        deleted_notification = db_fetchone(
            """
            SELECT related_pass_id
            FROM resident_notifications
            WHERE related_pass_id = %s
            """,
            (pass_id,),
        )

    assert deleted_row is None
    assert deleted_detail is None
    assert deleted_notification is None
