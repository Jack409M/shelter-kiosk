from __future__ import annotations


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


def test_post_without_csrf_token_is_blocked(client):
    response = client.post("/resident", data={"resident_code": "1234"}, follow_redirects=False)

    # should redirect due to CSRF failure
    assert response.status_code in (301, 302)


def test_post_with_invalid_csrf_token_is_blocked(client):
    _set_csrf_token(client, "correct-token")

    response = client.post(
        "/resident",
        data={
            "_csrf_token": "wrong-token",
            "resident_code": "1234",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)


def test_post_with_valid_csrf_token_allowed(client, monkeypatch):
    import routes.resident_requests as module

    csrf = _set_csrf_token(client)

    monkeypatch.setattr(module, "is_rate_limited", lambda *args, **kwargs: False)
    monkeypatch.setattr(module, "_load_resident_by_code", lambda code: None)
    monkeypatch.setattr(module, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_client_ip", lambda: "127.0.0.1")

    response = client.post(
        "/resident",
        data={
            "_csrf_token": csrf,
            "resident_code": "bad-code",
        },
        follow_redirects=False,
    )

    # should reach route logic (not CSRF block)
    assert response.status_code == 401


def test_csrf_header_token_allowed(client, monkeypatch):
    import routes.resident_requests as module

    csrf = _set_csrf_token(client)

    monkeypatch.setattr(module, "is_rate_limited", lambda *args, **kwargs: False)
    monkeypatch.setattr(module, "_load_resident_by_code", lambda code: None)
    monkeypatch.setattr(module, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_client_ip", lambda: "127.0.0.1")

    response = client.post(
        "/resident",
        headers={"X-CSRF-Token": csrf},
        data={"resident_code": "bad-code"},
        follow_redirects=False,
    )

    assert response.status_code == 401


def test_csrf_exempt_endpoint_allows_post_without_token(client):
    # sms consent is explicitly exempt
    response = client.post("/sms-consent", follow_redirects=False)

    # should NOT be blocked by CSRF
    assert response.status_code != 302


def test_csrf_failure_redirects_resident_to_public_home(client):
    _login_resident(client)

    response = client.post("/transport", data={}, follow_redirects=False)

    # resident context → should redirect safely
    assert response.status_code in (301, 302)
    assert "/" in response.headers["Location"]


def test_csrf_failure_redirects_staff_to_login(client):
    response = client.post("/staff/login", data={}, follow_redirects=False)

    assert response.status_code in (301, 302)
    assert "/staff/login" in response.headers["Location"]
