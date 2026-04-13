from __future__ import annotations


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _set_resident_session(client):
    with client.session_transaction() as session:
        session["resident_id"] = 1
        session["resident_identifier"] = "R-000001"
        session["resident_first"] = "Jane"
        session["resident_last"] = "Doe"
        session["resident_shelter"] = "abba"
        session["sms_consent_done"] = True


def test_resident_signin_invalid_code(client, monkeypatch):
    import routes.resident_requests as rr

    monkeypatch.setattr(rr, "init_db", lambda: None)
    monkeypatch.setattr(rr, "_load_resident_by_code", lambda code: None)
    monkeypatch.setattr(rr, "is_rate_limited", lambda *args, **kwargs: False)
    monkeypatch.setattr(rr, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        "/resident",
        data={"resident_code": "BADCODE"},
        follow_redirects=True,
    )

    assert response.status_code in (200, 401)
    assert b"Invalid Resident Code" in response.data


def test_resident_signin_success_sets_session(client, monkeypatch):
    import routes.resident_requests as rr

    monkeypatch.setattr(rr, "init_db", lambda: None)
    monkeypatch.setattr(rr, "is_rate_limited", lambda *args, **kwargs: False)
    monkeypatch.setattr(rr, "log_action", lambda *args, **kwargs: None)

    monkeypatch.setattr(
        rr,
        "_load_resident_by_code",
        lambda code: {
            "id": 1,
            "shelter": "abba",
            "first_name": "Jane",
            "last_name": "Doe",
        },
    )

    monkeypatch.setattr(
        rr,
        "resident_session_start",
        lambda row, shelter, code: (
            __import__("flask").session.update(
                {
                    "resident_id": 1,
                    "resident_identifier": "R-000001",
                    "resident_first": "Jane",
                    "resident_last": "Doe",
                    "resident_shelter": shelter,
                    "sms_consent_done": True,
                }
            )
        ),
    )

    response = client.post(
        "/resident",
        data={"resident_code": "GOODCODE"},
        follow_redirects=False,
    )

    assert response.status_code == 302

    with client.session_transaction() as session:
        assert session["resident_id"] == 1
        assert session["resident_shelter"] == "abba"


def test_transport_requires_required_fields(client, monkeypatch):
    import routes.resident_requests as rr

    _set_resident_session(client)

    monkeypatch.setattr(rr, "init_db", lambda: None)

    response = client.post(
        "/transport",
        data={},
        follow_redirects=True,
    )

    assert response.status_code == 400
    assert b"Complete all required fields" in response.data


def test_transport_rejects_past_time(client, monkeypatch):
    import routes.resident_requests as rr

    _set_resident_session(client)

    monkeypatch.setattr(rr, "init_db", lambda: None)

    monkeypatch.setattr(
        rr,
        "_parse_transport_needed_at",
        lambda raw: (None, "Needed time cannot be in the past."),
    )

    response = client.post(
        "/transport",
        data={
            "needed_at": "2020-01-01T00:00",
            "pickup_location": "A",
            "destination": "B",
        },
        follow_redirects=True,
    )

    assert response.status_code == 400
    assert b"Needed time cannot be in the past" in response.data


def test_transport_success_flow(client, monkeypatch):
    import routes.resident_requests as rr

    _set_resident_session(client)

    monkeypatch.setattr(rr, "init_db", lambda: None)
    monkeypatch.setattr(rr, "is_rate_limited", lambda *args, **kwargs: False)
    monkeypatch.setattr(rr, "log_action", lambda *args, **kwargs: None)

    monkeypatch.setattr(
        rr,
        "_parse_transport_needed_at",
        lambda raw: (__import__("datetime").datetime.utcnow(), None),
    )

    monkeypatch.setattr(
        rr,
        "_insert_transport_request",
        lambda **kwargs: 123,
    )

    response = client.post(
        "/transport",
        data={
            "needed_at": "2026-04-12T10:00",
            "pickup_location": "Shelter",
            "destination": "Clinic",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/resident/home" in response.headers["Location"]
