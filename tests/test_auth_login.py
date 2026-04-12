from __future__ import annotations

from werkzeug.security import generate_password_hash

from core.runtime import init_db


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _insert_staff_user(
    app,
    *,
    username: str,
    password: str,
    role: str = "admin",
    is_active: bool = True,
) -> None:
    from core.db import db_execute

    with app.app_context():
        init_db()

        db_execute(
            """
            DELETE FROM staff_shelter_assignments
            WHERE staff_user_id IN (
                SELECT id
                FROM staff_users
                WHERE LOWER(username) = LOWER(%s)
            )
            """,
            (username,),
        )

        db_execute(
            """
            DELETE FROM staff_users
            WHERE LOWER(username) = LOWER(%s)
            """,
            (username,),
        )

        db_execute(
            """
            INSERT INTO staff_users (
                username,
                password_hash,
                role,
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                username,
                generate_password_hash(password),
                role,
                is_active,
                "2026-01-01T00:00:00",
            ),
        )


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


def test_staff_login_success_redirects(app, client, monkeypatch):
    import routes.auth as auth_module

    _insert_staff_user(
        app,
        username="admin",
        password="secret123",
        role="admin",
        is_active=True,
    )

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
        assert session["staff_user_id"] > 0
        assert session["username"] == "admin"
        assert session["role"] == "admin"
        assert session["shelter"] == "abba"
        assert session["allowed_shelters"] == ["abba", "haven house", "gratitude house"] or session["allowed_shelters"] == ["abba house", "haven house", "gratitude house"] or session["allowed_shelters"] == ["abba", "haven", "gratitude"]


def test_staff_login_invalid_password_returns_401(app, client, monkeypatch):
    import routes.auth as auth_module

    _insert_staff_user(
        app,
        username="admin",
        password="correct-password",
        role="admin",
        is_active=True,
    )

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
