from __future__ import annotations

from flask import session


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
        data={"_csrf_token": _set_csrf_token(client), "resident_code": "BADCODE"},
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
        lambda row, shelter, code: session.update(
            {
                "resident_id": 1,
                "resident_identifier": "R-000001",
                "resident_first": "Jane",
                "resident_last": "Doe",
                "resident_shelter": shelter,
                "sms_consent_done": True,
            }
        ),
    )

    response = client.post(
        "/resident",
        data={"_csrf_token": _set_csrf_token(client), "resident_code": "GOODCODE"},
        follow_redirects=False,
    )

    assert response.status_code == 302

    with client.session_transaction() as session_state:
        assert session_state["resident_id"] == 1
        assert session_state["resident_shelter"] == "abba"


def test_resident_signin_clears_old_session_state_before_starting_new_one(client, monkeypatch):
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

    def _fake_resident_session_start(row, shelter, code):
        assert "role" not in session
        assert "username" not in session
        assert "staff_user_id" not in session
        assert "resident_id" not in session
        assert "resident_identifier" not in session

        session.update(
            {
                "resident_id": 1,
                "resident_identifier": "R-000001",
                "resident_first": "Jane",
                "resident_last": "Doe",
                "resident_shelter": shelter,
                "sms_consent_done": True,
            }
        )

    monkeypatch.setattr(rr, "resident_session_start", _fake_resident_session_start)

    with client.session_transaction() as session_state:
        session_state["role"] = "admin"
        session_state["username"] = "old-staff-user"
        session_state["staff_user_id"] = 999
        session_state["resident_id"] = 777
        session_state["resident_identifier"] = "STALE"
        session_state["resident_first"] = "Old"
        session_state["resident_last"] = "Resident"
        session_state["resident_shelter"] = "haven"

    response = client.post(
        "/resident",
        data={"_csrf_token": _set_csrf_token(client), "resident_code": "GOODCODE"},
        follow_redirects=False,
    )

    assert response.status_code == 302

    with client.session_transaction() as session_state:
        assert session_state["resident_id"] == 1
        assert session_state["resident_identifier"] == "R-000001"
        assert session_state["resident_shelter"] == "abba"
        assert "role" not in session_state
        assert "username" not in session_state
        assert "staff_user_id" not in session_state


def test_resident_signin_rejects_unapproved_next_url(client, monkeypatch):
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
        lambda row, shelter, code: session.update(
            {
                "resident_id": 1,
                "resident_identifier": "R-000001",
                "resident_first": "Jane",
                "resident_last": "Doe",
                "resident_shelter": shelter,
                "sms_consent_done": True,
            }
        ),
    )

    response = client.post(
        "/resident?next=/admin",
        data={"_csrf_token": _set_csrf_token(client), "resident_code": "GOODCODE"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/resident/home")


def test_resident_signin_allows_approved_next_url(client, monkeypatch):
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
        lambda row, shelter, code: session.update(
            {
                "resident_id": 1,
                "resident_identifier": "R-000001",
                "resident_first": "Jane",
                "resident_last": "Doe",
                "resident_shelter": shelter,
                "sms_consent_done": True,
            }
        ),
    )

    response = client.post(
        "/resident?next=/transport",
        data={"_csrf_token": _set_csrf_token(client), "resident_code": "GOODCODE"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/transport")


def test_resident_signin_without_consent_redirects_to_consent_with_safe_next(client, monkeypatch):
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
        lambda row, shelter, code: session.update(
            {
                "resident_id": 1,
                "resident_identifier": "R-000001",
                "resident_first": "Jane",
                "resident_last": "Doe",
                "resident_shelter": shelter,
                "sms_consent_done": False,
            }
        ),
    )

    response = client.post(
        "/resident?next=/transport",
        data={"_csrf_token": _set_csrf_token(client), "resident_code": "GOODCODE"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/resident/consent" in response.headers["Location"]
    assert "next=/transport" in response.headers["Location"]


def test_resident_home_redirects_when_session_is_partial(client, monkeypatch):
    with client.session_transaction() as session_state:
        session_state["resident_id"] = 1
        session_state["resident_identifier"] = "R-000001"
        session_state["resident_first"] = "Jane"
        session_state["resident_shelter"] = "abba"
        session_state["sms_consent_done"] = True

    response = client.get("/resident/home", follow_redirects=False)

    assert response.status_code == 302
    assert "/resident?next=/resident/home" in response.headers["Location"]

    with client.session_transaction() as session_state:
        assert "resident_id" not in session_state
        assert "resident_identifier" not in session_state
        assert "resident_first" not in session_state
        assert "resident_shelter" not in session_state


def test_resident_chores_redirects_when_session_is_corrupted(client, monkeypatch):
    with client.session_transaction() as session_state:
        session_state["resident_id"] = "not-an-int"
        session_state["resident_identifier"] = "R-000001"
        session_state["resident_first"] = "Jane"
        session_state["resident_last"] = "Doe"
        session_state["resident_shelter"] = "abba"
        session_state["sms_consent_done"] = True

    response = client.get("/resident/chores", follow_redirects=False)

    assert response.status_code == 302
    assert "/resident?next=/resident/chores" in response.headers["Location"]

    with client.session_transaction() as session_state:
        assert "resident_id" not in session_state
        assert "resident_identifier" not in session_state
        assert "resident_first" not in session_state
        assert "resident_last" not in session_state
        assert "resident_shelter" not in session_state


def test_resident_logout_clears_session(client):
    _set_resident_session(client)

    with client.session_transaction() as session_state:
        session_state["resident_phone"] = "5551212"

    response = client.get("/resident/logout", follow_redirects=False)

    assert response.status_code == 302

    with client.session_transaction() as session_state:
        assert dict(session_state) == {}


def test_transport_requires_required_fields(client, monkeypatch):
    import routes.resident_requests as rr

    _set_resident_session(client)

    monkeypatch.setattr(rr, "init_db", lambda: None)

    response = client.post(
        "/transport",
        data={"_csrf_token": _set_csrf_token(client)},
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
            "_csrf_token": _set_csrf_token(client),
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
            "_csrf_token": _set_csrf_token(client),
            "needed_at": "2026-04-12T10:00",
            "pickup_location": "Shelter",
            "destination": "Clinic",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/resident/home" in response.headers["Location"]
