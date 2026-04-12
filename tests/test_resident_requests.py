from __future__ import annotations

from core.runtime import init_db


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _login_resident(client) -> None:
    with client.session_transaction() as session:
        session["resident_id"] = 123
        session["resident_identifier"] = "RID-123"
        session["resident_first"] = "Test"
        session["resident_last"] = "Resident"
        session["resident_shelter"] = "abba"
        session["sms_consent_done"] = True


def _insert_resident(
    app,
    *,
    resident_identifier: str,
    resident_code: str,
    first_name: str,
    last_name: str,
    shelter: str,
) -> None:
    from core.db import db_execute

    with app.app_context():
        init_db()

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
                first_name,
                last_name,
                shelter,
                True,
                "2026-01-01T00:00:00",
            ),
        )


def test_resident_signin_page_loads(client):
    response = client.get("/resident", follow_redirects=True)

    assert response.status_code == 200


def test_resident_signin_invalid_code_returns_401(client, monkeypatch):
    import routes.resident_requests as module

    csrf_token = _set_csrf_token(client)

    monkeypatch.setattr(module, "_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(module, "is_rate_limited", lambda key, limit, window_seconds: False)
    monkeypatch.setattr(module, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        "/resident",
        data={
            "_csrf_token": csrf_token,
            "resident_code": "bad-code",
        },
        follow_redirects=False,
    )

    assert response.status_code == 401


def test_resident_signin_success_sets_session_and_redirects_to_consent(app, client, monkeypatch):
    import routes.resident_requests as module

    _insert_resident(
        app,
        resident_identifier="resident_signin_test",
        resident_code="11112222",
        first_name="Jane",
        last_name="Doe",
        shelter="abba",
    )

    csrf_token = _set_csrf_token(client)

    monkeypatch.setattr(module, "_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(module, "is_rate_limited", lambda key, limit, window_seconds: False)
    monkeypatch.setattr(module, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        "/resident",
        data={
            "_csrf_token": csrf_token,
            "resident_code": "11112222",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/resident/consent" in response.headers["Location"]

    with client.session_transaction() as session:
        assert session["resident_identifier"] == "resident_signin_test"
        assert session["resident_first"] == "Jane"
        assert session["resident_last"] == "Doe"
        assert session["resident_shelter"] == "abba"
        assert session["resident_code"] == "11112222"


def test_resident_transport_requires_login(client):
    response = client.get("/transport", follow_redirects=False)

    assert response.status_code in (301, 302)
    assert "/resident" in response.headers["Location"]


def test_resident_transport_page_loads_when_logged_in(client, monkeypatch):
    import routes.resident_requests as module

    _login_resident(client)
    monkeypatch.setattr(module, "init_db", lambda: None)

    response = client.get("/transport", follow_redirects=True)

    assert response.status_code == 200
