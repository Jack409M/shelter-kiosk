from __future__ import annotations

from datetime import datetime


def _login_resident(client):
    with client.session_transaction() as session:
        session["resident_id"] = 123
        session["resident_identifier"] = "RID-123"
        session["resident_first"] = "Test"
        session["resident_last"] = "Resident"
        session["resident_shelter"] = "abba"
        session["sms_consent_done"] = True


def test_resident_signin_page_loads(client):
    response = client.get("/resident", follow_redirects=True)

    assert response.status_code == 200


def test_resident_transport_requires_login(client):
    response = client.get("/transport", follow_redirects=False)

    assert response.status_code in (301, 302)


def test_resident_transport_page_loads_when_logged_in(client, monkeypatch):
    import routes.resident_requests as module

    _login_resident(client)

    monkeypatch.setattr(module, "init_db", lambda: None)

    response = client.get("/transport", follow_redirects=True)

    assert response.status_code == 200


def test_resident_can_submit_transport_request(client, monkeypatch):
    import routes.resident_requests as module

    _login_resident(client)

    monkeypatch.setattr(module, "init_db", lambda: None)
    monkeypatch.setattr(module, "is_rate_limited", lambda key, limit, window_seconds: False)
    monkeypatch.setattr(module, "_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(module, "_parse_transport_needed_at", lambda value: (datetime.utcnow(), None))
    monkeypatch.setattr(module, "_insert_transport_request", lambda **kwargs: 1)
    monkeypatch.setattr(module, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        "/transport",
        data={
            "needed_at": "2030-01-01 10:00 AM",
            "pickup_location": "Shelter",
            "destination": "Clinic",
            "reason": "Appointment",
            "resident_notes": "Test",
            "callback_phone": "555-111-2222",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert response.headers["Location"].endswith("/")
