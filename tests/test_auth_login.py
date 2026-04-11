from __future__ import annotations

from werkzeug.security import generate_password_hash


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def test_staff_login_get_renders(client, monkeypatch):
    import routes.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba House", "Haven House", "Gratitude House"],
    )

    response = client.get("/staff/login", follow_redirects=True)

    assert response.status_code == 200
    assert (
        b"Abba House" in response.data
        or b"Haven House" in response.data
        or b"Gratitude House" in response.data
    )


def test_staff_login_success_redirects(client, monkeypatch):
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
    monkeypatch.setattr(auth_module, "is_rate_limited", lambda key, limit, window_seconds: False)
    monkeypatch.setattr(auth_module, "log_action", lambda *args, **kwargs: None)

    monkeypatch.setattr(
        auth_module,
        "_load_staff_user_by_username",
        lambda normalized_username: {
            "id": 1,
            "username": "admin",
            "password_hash": generate_password_hash("secret123"),
            "role": "admin",
            "is_active": 1,
        },
    )

    monkeypatch.setattr(
        auth_module,
        "_load_allowed_shelters_for_user",
        lambda **kwargs: ["abba", "haven", "gratitude"],
    )

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

    assert response.status_code == 302
    assert "/staff/admin/dashboard" in response.headers["Location"]

    with client.session_transaction() as session:
        assert session["staff_user_id"] == 1
        assert session["username"] == "admin"
        assert session["role"] == "admin"
        assert session["shelter"] == "abba"
        assert session["allowed_shelters"] == ["abba", "haven", "gratitude"]


def test_staff_login_invalid_password_returns_401(client, monkeypatch):
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
    monkeypatch.setattr(auth_module, "is_rate_limited", lambda key, limit, window_seconds: False)
    monkeypatch.setattr(auth_module, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth_module, "_record_failed_login_attempt", lambda **kwargs: None)

    monkeypatch.setattr(
        auth_module,
        "_load_staff_user_by_username",
        lambda normalized_username: {
            "id": 1,
            "username": "admin",
            "password_hash": generate_password_hash("correct-password"),
            "role": "admin",
            "is_active": 1,
        },
    )

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": csrf_token,
            "username": "admin",
            "password": "wrong-password",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 401
