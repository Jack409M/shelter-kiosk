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
            "shelter": "abba house",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/staff/admin/dashboard" in response.headers["Location"]

    with client.session_transaction() as session:
        assert session["staff_user_id"] > 0
        assert session["username"] == "admin"
        assert session["role"] == "admin"
        assert session["shelter"] in {"abba", "abba house"}
        assert session["allowed_shelters"] in (
            ["abba", "haven house", "gratitude house"],
            ["abba house", "haven house", "gratitude house"],
            ["abba", "haven", "gratitude"],
        )


def test_staff_login_clears_old_session_before_setting_new_staff_session(app, client, monkeypatch):
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

    original_set_staff_session = auth_module._set_staff_session

    def _wrapped_set_staff_session(**kwargs):
        from flask import session

        assert "resident_id" not in session
        assert "resident_identifier" not in session
        assert "role" not in session
        assert "username" not in session
        return original_set_staff_session(**kwargs)

    monkeypatch.setattr(auth_module, "_set_staff_session", _wrapped_set_staff_session)

    with client.session_transaction() as session:
        session["resident_id"] = 999
        session["resident_identifier"] = "R-OLD"
        session["role"] = "case_manager"
        session["username"] = "stale-user"
        session["staff_user_id"] = 444

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": csrf_token,
            "username": "admin",
            "password": "secret123",
            "shelter": "abba house",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with client.session_transaction() as session:
        assert session["username"] == "admin"
        assert session["role"] == "admin"
        assert "resident_id" not in session
        assert "resident_identifier" not in session


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


def test_staff_login_inactive_user_returns_401(app, client, monkeypatch):
    import routes.auth as auth_module

    _insert_staff_user(
        app,
        username="inactive-admin",
        password="secret123",
        role="admin",
        is_active=False,
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
            "username": "inactive-admin",
            "password": "secret123",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 401


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
    monkeypatch.setattr(auth_module, "get_key_lock_seconds_remaining", lambda key: 123)
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


def test_staff_login_rejects_shelter_outside_allowed_assignments(app, client, monkeypatch):
    import routes.auth as auth_module

    _insert_staff_user(
        app,
        username="casey",
        password="secret123",
        role="case_manager",
        is_active=True,
    )

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba", "Haven", "Gratitude"],
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
        "_load_allowed_shelters_for_user",
        lambda **kwargs: ["abba"],
    )

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": csrf_token,
            "username": "casey",
            "password": "secret123",
            "shelter": "haven",
        },
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_staff_login_denies_user_with_no_assigned_shelters(app, client, monkeypatch):
    import routes.auth as auth_module

    _insert_staff_user(
        app,
        username="casey",
        password="secret123",
        role="case_manager",
        is_active=True,
    )

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba", "Haven", "Gratitude"],
    )
    monkeypatch.setattr(auth_module, "get_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(auth_module, "is_ip_banned", lambda ip: False)
    monkeypatch.setattr(auth_module, "is_key_locked", lambda key: False)
    monkeypatch.setattr(auth_module, "get_key_lock_seconds_remaining", lambda key: 0)
    monkeypatch.setattr(auth_module, "is_rate_limited", lambda key, limit, window_seconds: False)
    monkeypatch.setattr(auth_module, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth_module, "_load_allowed_shelters_for_user", lambda **kwargs: [])

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": csrf_token,
            "username": "casey",
            "password": "secret123",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 403
