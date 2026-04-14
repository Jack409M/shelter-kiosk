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


def _insert_resident(
    app,
    *,
    resident_identifier: str,
    resident_code: str,
    shelter: str = "abba",
    program_level: str = "5",
) -> int:
    from core.db import db_execute, db_fetchone

    with app.app_context():
        init_db()

        db_execute(
            """
            DELETE FROM transport_requests
            WHERE resident_identifier = %s
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
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resident_identifier,
                resident_code,
                "Jane",
                "Resident",
                shelter,
                program_level,
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


def test_real_pass_rate_limit_blocks_repeated_submissions(app, client, monkeypatch):
    import routes.resident_parts.pass_request as resident_pass_module
    from core.db import db_fetchall

    resident_id = _insert_resident(
        app,
        resident_identifier="abuse_pass_resident",
        resident_code="77000001",
    )
    _login_resident(
        client,
        resident_id=resident_id,
        resident_identifier="abuse_pass_resident",
    )

    monkeypatch.setattr(
        resident_pass_module,
        "calculate_prior_week_attendance_hours",
        lambda resident_id, shelter: None,
    )
    monkeypatch.setattr(resident_pass_module, "log_action", lambda *args, **kwargs: None)

    last_response = None

    for _ in range(7):
        csrf_token = _set_csrf_token(client)
        last_response = client.post(
            "/pass-request",
            data={
                "_csrf_token": csrf_token,
                "pass_type": "pass",
                "destination": "Clinic",
                "reason": "Appointment",
                "resident_notes": "Repeated request",
                "request_date": "2099-01-01",
                "requirements_acknowledged": "yes",
                "resident_phone": "5551112222",
                "start_at": "2099-01-01T10:00",
                "end_at": "2099-01-01T18:00",
            },
            follow_redirects=False,
        )

    assert last_response is not None
    assert last_response.status_code == 429

    with app.app_context():
        rows = db_fetchall(
            """
            SELECT id
            FROM resident_passes
            WHERE resident_id = %s
            """,
            (resident_id,),
        )

    # Only one active pass is allowed per resident; rate limiting should still trigger.
    assert len(rows) == 1


def test_real_transport_rate_limit_blocks_repeated_submissions(app, client):
    from core.db import db_fetchall

    resident_id = _insert_resident(
        app,
        resident_identifier="abuse_transport_resident",
        resident_code="77000002",
    )
    _login_resident(
        client,
        resident_id=resident_id,
        resident_identifier="abuse_transport_resident",
    )

    last_response = None

    for i in range(7):
        csrf_token = _set_csrf_token(client)
        last_response = client.post(
            "/transport",
            data={
                "_csrf_token": csrf_token,
                "needed_at": f"2099-01-01 {i + 1:02d}:00 PM",
                "pickup_location": "Abba House",
                "destination": "Clinic",
                "reason": "Appointment",
                "resident_notes": "Repeated transport",
                "callback_phone": "5551112222",
            },
            follow_redirects=False,
        )

    assert last_response is not None
    assert last_response.status_code == 429

    with app.app_context():
        rows = db_fetchall(
            """
            SELECT id
            FROM transport_requests
            WHERE resident_identifier = %s
            """,
            ("abuse_transport_resident",),
        )

    assert len(rows) == 6


def test_malformed_pass_payload_fails_cleanly_without_insert(app, client, monkeypatch):
    import routes.resident_parts.pass_request as resident_pass_module
    from core.db import db_fetchall

    resident_id = _insert_resident(
        app,
        resident_identifier="bad_pass_payload_resident",
        resident_code="77000003",
    )
    _login_resident(
        client,
        resident_id=resident_id,
        resident_identifier="bad_pass_payload_resident",
    )

    monkeypatch.setattr(
        resident_pass_module,
        "calculate_prior_week_attendance_hours",
        lambda resident_id, shelter: None,
    )
    monkeypatch.setattr(resident_pass_module, "log_action", lambda *args, **kwargs: None)

    csrf_token = _set_csrf_token(client)
    response = client.post(
        "/pass-request",
        data={
            "_csrf_token": csrf_token,
            "pass_type": "pass",
            "destination": "Clinic",
            "reason": "Appointment",
            "request_date": "2099-01-01",
            "requirements_acknowledged": "yes",
            "resident_phone": "5551112222",
            "start_at": "not-a-date",
            "end_at": "still-not-a-date",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400

    with app.app_context():
        rows = db_fetchall(
            """
            SELECT id
            FROM resident_passes
            WHERE resident_id = %s
            """,
            (resident_id,),
        )

    assert rows == []


def test_malformed_transport_payload_fails_cleanly_without_insert(app, client):
    from core.db import db_fetchall

    resident_id = _insert_resident(
        app,
        resident_identifier="bad_transport_payload_resident",
        resident_code="77000004",
    )
    _login_resident(
        client,
        resident_id=resident_id,
        resident_identifier="bad_transport_payload_resident",
    )

    csrf_token = _set_csrf_token(client)
    response = client.post(
        "/transport",
        data={
            "_csrf_token": csrf_token,
            "needed_at": "not-a-date",
            "pickup_location": "Abba House",
            "destination": "Clinic",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400

    with app.app_context():
        rows = db_fetchall(
            """
            SELECT id
            FROM transport_requests
            WHERE resident_identifier = %s
            """,
            ("bad_transport_payload_resident",),
        )

    assert rows == []
