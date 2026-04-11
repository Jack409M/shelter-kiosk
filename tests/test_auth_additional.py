from __future__ import annotations


def test_staff_login_page_loads(client, monkeypatch):
    import routes.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba House", "Haven House", "Gratitude House"],
    )

    response = client.get("/staff/login", follow_redirects=False)

    assert response.status_code == 200


def test_staff_login_requires_valid_credentials(client, monkeypatch):
    import routes.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba House", "Haven House", "Gratitude House"],
    )
    monkeypatch.setattr(auth_module, "get_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(auth_module, "is_ip_banned", lambda ip: False)
    monkeypatch.setattr(auth_module, "is_key_locked", lambda key: False)
    monkeypatch.setattr(auth_module, "get_key_lock_seconds_remaining", lambda key: 0)
    monkeypatch.setattr(auth_module, "is_rate_limited", lambda *args, **kwargs: False)
    monkeypatch.setattr(auth_module, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth_module, "_record_failed_login_attempt", lambda **kwargs: None)
    monkeypatch.setattr(auth_module, "_load_staff_user_by_username", lambda normalized_username: None)

    with client.session_transaction() as session:
        session["_csrf_token"] = "test-csrf-token"

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": "test-csrf-token",
            "username": "missing-user",
            "password": "wrongpassword",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 401


def test_staff_login_requires_username(client, monkeypatch):
    import routes.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba House", "Haven House", "Gratitude House"],
    )
    monkeypatch.setattr(auth_module, "get_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(auth_module, "is_ip_banned", lambda ip: False)
    monkeypatch.setattr(auth_module, "is_key_locked", lambda key: False)
    monkeypatch.setattr(auth_module, "get_key_lock_seconds_remaining", lambda key: 0)
    monkeypatch.setattr(auth_module, "is_rate_limited", lambda *args, **kwargs: False)
    monkeypatch.setattr(auth_module, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth_module, "_record_failed_login_attempt", lambda **kwargs: None)
    monkeypatch.setattr(auth_module, "_load_staff_user_by_username", lambda normalized_username: None)

    with client.session_transaction() as session:
        session["_csrf_token"] = "test-csrf-token"

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": "test-csrf-token",
            "username": "",
            "password": "whatever",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 401


def test_staff_logout_clears_session(client, monkeypatch):
    import routes.auth as auth_module

    monkeypatch.setattr(auth_module, "log_action", lambda *args, **kwargs: None)

    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = "admin"
        session["shelter"] = "abba"

    response = client.get("/staff/logout", follow_redirects=False)

    assert response.status_code in (301, 302)

    with client.session_transaction() as session:
        assert "staff_user_id" not in session
        assert "username" not in session
        assert "role" not in session
        assert "shelter" not in session
