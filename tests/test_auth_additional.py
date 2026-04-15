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


def _set_staff_session(
    client,
    *,
    staff_user_id: int = 1,
    username: str = "staff",
    role: str = "admin",
    shelter: str = "abba",
    allowed_shelters: list[str] | None = None,
) -> None:
    with client.session_transaction() as session:
        session["staff_user_id"] = staff_user_id
        session["username"] = username
        session["role"] = role
        session["shelter"] = shelter
        session["allowed_shelters"] = allowed_shelters or ["abba", "haven", "gratitude"]


def test_staff_login_page_loads(client, monkeypatch):
    import routes.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba House", "Haven House", "Gratitude House"],
    )

    response = client.get("/staff/login", follow_redirects=False)

    assert response.status_code == 200


def test_staff_login_requires_valid_credentials(app, client, monkeypatch):
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

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": csrf_token,
            "username": "missing-user",
            "password": "wrongpassword",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 401


def test_staff_login_requires_username(app, client, monkeypatch):
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
    monkeypatch.setattr(auth_module, "is_rate_limited", lambda *args, **kwargs: False)
    monkeypatch.setattr(auth_module, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth_module, "_record_failed_login_attempt", lambda **kwargs: None)

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": csrf_token,
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
    assert "/staff/login" in response.headers["Location"]

    with client.session_transaction() as session:
        assert "staff_user_id" not in session
        assert "username" not in session
        assert "role" not in session
        assert "shelter" not in session


def test_staff_select_shelter_get_filters_to_allowed_shelters(client, monkeypatch):
    import routes.auth as auth_module

    _set_staff_session(
        client,
        allowed_shelters=["abba", "gratitude"],
    )

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba", "Haven", "Gratitude"],
    )

    response = client.get("/staff/select-shelter", follow_redirects=False)

    assert response.status_code == 200
    assert b"Abba" in response.data
    assert b"Gratitude" in response.data
    assert b"Haven" not in response.data


def test_staff_select_shelter_rejects_invalid_shelter(client, monkeypatch):
    import routes.auth as auth_module

    _set_staff_session(
        client,
        allowed_shelters=["abba"],
    )

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba", "Haven", "Gratitude"],
    )

    response = client.post(
        "/staff/select-shelter",
        data={
            "_csrf_token": _set_csrf_token(client),
            "shelter": "haven",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/select-shelter" in response.headers["Location"]

    with client.session_transaction() as session:
        assert session["shelter"] == "abba"


def test_staff_select_shelter_accepts_valid_shelter_and_updates_session(client, monkeypatch):
    import routes.auth as auth_module

    _set_staff_session(
        client,
        allowed_shelters=["abba", "gratitude"],
    )

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba", "Haven", "Gratitude"],
    )

    response = client.post(
        "/staff/select-shelter",
        data={
            "_csrf_token": _set_csrf_token(client),
            "shelter": "gratitude",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/attendance" in response.headers["Location"]

    with client.session_transaction() as session:
        assert session["shelter"] == "gratitude"


def test_staff_select_shelter_allows_safe_staff_next_path(client, monkeypatch):
    import routes.auth as auth_module

    _set_staff_session(
        client,
        allowed_shelters=["abba", "gratitude"],
    )

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba", "Haven", "Gratitude"],
    )

    response = client.post(
        "/staff/select-shelter",
        data={
            "_csrf_token": _set_csrf_token(client),
            "shelter": "gratitude",
            "next": "/staff/profile",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert response.headers["Location"].endswith("/staff/profile")


def test_staff_select_shelter_rejects_non_staff_next_path(client, monkeypatch):
    import routes.auth as auth_module

    _set_staff_session(
        client,
        allowed_shelters=["abba", "gratitude"],
    )

    monkeypatch.setattr(
        auth_module,
        "get_all_shelters",
        lambda: ["Abba", "Haven", "Gratitude"],
    )

    response = client.post(
        "/staff/select-shelter",
        data={
            "_csrf_token": _set_csrf_token(client),
            "shelter": "gratitude",
            "next": "/admin",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert response.headers["Location"].endswith("/staff/attendance")
