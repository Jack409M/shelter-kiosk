from __future__ import annotations

from core.runtime import init_db


def _login_resident_session(client) -> None:
    with client.session_transaction() as session:
        session["resident_id"] = 1
        session["resident_identifier"] = "test_resident"
        session["resident_first"] = "Res"
        session["resident_last"] = "User"
        session["resident_shelter"] = "abba"
        session["sms_consent_done"] = True


def test_resident_signin_page_loads(client):
    response = client.get("/resident", follow_redirects=False)

    assert response.status_code == 200


def test_resident_signin_invalid_code_returns_401(client, monkeypatch):
    import routes.resident_requests as resident_requests_module

    monkeypatch.setattr(resident_requests_module, "init_db", lambda: None)
    monkeypatch.setattr(resident_requests_module, "_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(resident_requests_module, "is_rate_limited", lambda *args, **kwargs: False)
    monkeypatch.setattr(resident_requests_module, "_load_resident_by_code", lambda resident_code: None)
    monkeypatch.setattr(resident_requests_module, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        "/resident",
        data={"resident_code": "bad-code"},
        follow_redirects=False,
    )

    assert response.status_code == 401


def test_resident_transport_requires_login_redirects(client):
    response = client.get("/transport", follow_redirects=False)

    assert response.status_code in (301, 302)


def test_resident_transport_page_loads_for_logged_in_resident(client):
    _login_resident_session(client)

    response = client.get("/transport", follow_redirects=False)

    assert response.status_code == 200


def test_resident_transport_post_missing_required_fields_returns_400(app, client, monkeypatch):
    import routes.resident_requests as resident_requests_module

    _login_resident_session(client)

    with app.app_context():
        init_db()

    monkeypatch.setattr(resident_requests_module, "init_db", lambda: None)
    monkeypatch.setattr(resident_requests_module, "_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(resident_requests_module, "is_rate_limited", lambda *args, **kwargs: False)

    response = client.post(
        "/transport",
        data={
            "needed_at": "",
            "pickup_location": "",
            "destination": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400


def test_resident_transport_post_success_redirects(app, client, monkeypatch):
    from core.db import db_execute, db_fetchall
    import routes.resident_requests as resident_requests_module

    _login_resident_session(client)

    with app.app_context():
        init_db()

        db_execute(
            """
            DELETE FROM transport_requests
            WHERE resident_identifier = %s
            """,
            ("test_resident",),
        )

    monkeypatch.setattr(resident_requests_module, "init_db", lambda: None)
    monkeypatch.setattr(resident_requests_module, "_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(resident_requests_module, "is_rate_limited", lambda *args, **kwargs: False)
    monkeypatch.setattr(resident_requests_module, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        "/transport",
        data={
            "needed_at": "2026-12-31 10:00",
            "pickup_location": "Abba House",
            "destination": "Clinic",
            "reason": "Appointment",
            "resident_notes": "Need ride",
            "callback_phone": "555-111-2222",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)

    with app.app_context():
        rows = db_fetchall(
            """
            SELECT resident_identifier, pickup_location, destination, status
            FROM transport_requests
            WHERE resident_identifier = %s
            ORDER BY id DESC
            """,
            ("test_resident",),
        )

    assert rows
    row = rows[0]
    assert row["resident_identifier"] == "test_resident"
    assert row["pickup_location"] == "Abba House"
    assert row["destination"] == "Clinic"
    assert row["status"] == "pending"
