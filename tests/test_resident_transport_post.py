from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.runtime import init_db

CHICAGO_TZ = ZoneInfo("America/Chicago")


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _login_resident(client):
    with client.session_transaction() as session:
        session["resident_id"] = 1
        session["resident_identifier"] = "RID-1"
        session["resident_first"] = "Jane"
        session["resident_last"] = "Doe"
        session["resident_shelter"] = "abba"
        session["sms_consent_done"] = True


def _valid_transport_payload():
    future_time = (datetime.now(CHICAGO_TZ) + timedelta(hours=2)).strftime("%Y-%m-%d %I:%M %p")

    return {
        "needed_at": future_time,
        "pickup_location": "Shelter",
        "destination": "Clinic",
        "reason": "Appointment",
        "resident_notes": "Test note",
        "callback_phone": "555-111-2222",
    }


def test_transport_post_requires_login(client):
    csrf = _set_csrf_token(client)

    response = client.post(
        "/transport",
        data={
            "_csrf_token": csrf,
            **_valid_transport_payload(),
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/resident" in response.headers["Location"]


def test_transport_post_missing_required_fields(client, monkeypatch):
    import routes.resident_requests as module

    _login_resident(client)
    csrf = _set_csrf_token(client)

    monkeypatch.setattr(module, "init_db", lambda: None)
    monkeypatch.setattr(module, "is_rate_limited", lambda *args, **kwargs: False)

    response = client.post(
        "/transport",
        data={
            "_csrf_token": csrf,
            "needed_at": "",  # missing
            "pickup_location": "",
            "destination": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 400
    assert b"Complete all required fields." in response.data


def test_transport_post_invalid_datetime(client, monkeypatch):
    import routes.resident_requests as module

    _login_resident(client)
    csrf = _set_csrf_token(client)

    monkeypatch.setattr(module, "init_db", lambda: None)
    monkeypatch.setattr(module, "is_rate_limited", lambda *args, **kwargs: False)

    response = client.post(
        "/transport",
        data={
            "_csrf_token": csrf,
            "needed_at": "bad-date",
            "pickup_location": "A",
            "destination": "B",
        },
        follow_redirects=True,
    )

    assert response.status_code == 400
    assert b"Invalid needed date or time." in response.data


def test_transport_post_past_datetime_rejected(client, monkeypatch):
    import routes.resident_requests as module

    _login_resident(client)
    csrf = _set_csrf_token(client)

    past_time = (datetime.now(CHICAGO_TZ) - timedelta(hours=2)).strftime("%Y-%m-%d %I:%M %p")

    monkeypatch.setattr(module, "init_db", lambda: None)
    monkeypatch.setattr(module, "is_rate_limited", lambda *args, **kwargs: False)

    response = client.post(
        "/transport",
        data={
            "_csrf_token": csrf,
            "needed_at": past_time,
            "pickup_location": "A",
            "destination": "B",
        },
        follow_redirects=True,
    )

    assert response.status_code == 400
    assert b"Needed time cannot be in the past." in response.data


def test_transport_post_rate_limited(client, monkeypatch):
    import routes.resident_requests as module

    _login_resident(client)
    csrf = _set_csrf_token(client)

    monkeypatch.setattr(module, "init_db", lambda: None)
    monkeypatch.setattr(module, "is_rate_limited", lambda *args, **kwargs: True)

    response = client.post(
        "/transport",
        data={
            "_csrf_token": csrf,
            **_valid_transport_payload(),
        },
        follow_redirects=True,
    )

    assert response.status_code == 429
    assert b"Too many transportation submissions" in response.data


def test_transport_post_success_writes_db_and_redirects(app, client, monkeypatch):
    import routes.resident_requests as module
    from core.db import db_fetchone

    _login_resident(client)
    csrf = _set_csrf_token(client)

    monkeypatch.setattr(module, "is_rate_limited", lambda *args, **kwargs: False)

    response = client.post(
        "/transport",
        data={
            "_csrf_token": csrf,
            **_valid_transport_payload(),
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/resident/home" in response.headers["Location"]

    # verify DB write
    with app.app_context():
        init_db()

        row = db_fetchone("SELECT * FROM transport_requests ORDER BY id DESC LIMIT 1")

        assert row is not None
        assert row["pickup_location"] == "Shelter"
        assert row["destination"] == "Clinic"
        assert row["status"] == "pending"
