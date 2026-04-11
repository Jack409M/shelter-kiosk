from __future__ import annotations


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def test_staff_login_banned_ip_returns_403(client, monkeypatch):
    import routes.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba House", "Haven House", "Gratitude House"],
    )
    monkeypatch.setattr(auth_module, "get_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(auth_module, "is_ip_banned", lambda ip: True)
    monkeypatch.setattr(auth_module, "log_action", lambda *args, **kwargs: None)

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": csrf_token,
            "username": "admin",
            "password": "secret123",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_staff_login_locked_username_returns_429(client, monkeypatch):
    import routes.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba House", "Haven House", "Gratitude House"],
    )
    monkeypatch.setattr(auth_module, "get_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(auth_module, "is_ip_banned", lambda ip: False)
    monkeypatch.setattr(auth_module, "is_key_locked", lambda key: True)
    monkeypatch.setattr(auth_module, "get_key_lock_seconds_remaining", lambda key: 120)
    monkeypatch.setattr(auth_module, "log_action", lambda *args, **kwargs: None)

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": csrf_token,
            "username": "admin",
            "password": "secret123",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 429
