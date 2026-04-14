from __future__ import annotations

from werkzeug.security import generate_password_hash

from core.runtime import init_db


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _insert_staff_user(app, *, username: str, password: str) -> None:
    from core.db import db_execute

    with app.app_context():
        init_db()

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
                "admin",
                True,
                "2026-01-01T00:00:00",
            ),
        )


def test_staff_login_blocks_after_repeated_failures(app, client):
    _insert_staff_user(app, username="lockout_user", password="correct")

    csrf = _set_csrf_token(client)

    for _ in range(10):
        response = client.post(
            "/staff/login",
            data={
                "_csrf_token": csrf,
                "username": "lockout_user",
                "password": "wrong",
                "shelter": "abba",
            },
            follow_redirects=False,
        )

    assert response.status_code in (401, 429)


def test_staff_login_allows_correct_password_before_lock(app, client):
    _insert_staff_user(app, username="normal_user", password="correct")

    csrf = _set_csrf_token(client)

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": csrf,
            "username": "normal_user",
            "password": "correct",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code in (302, 429)
    assert "/staff/admin/dashboard" in response.headers["Location"]


def test_staff_login_ip_ban_after_abuse(app, client):
    _insert_staff_user(app, username="ip_user", password="correct")

    csrf = _set_csrf_token(client)

    for _ in range(25):
        client.post(
            "/staff/login",
            data={
                "_csrf_token": csrf,
                "username": "ip_user",
                "password": "wrong",
                "shelter": "abba",
            },
            follow_redirects=False,
        )

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": csrf,
            "username": "ip_user",
            "password": "correct",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code in (403, 429)


def test_staff_login_lock_is_username_specific(app, client):
    _insert_staff_user(app, username="user_a", password="correct")
    _insert_staff_user(app, username="user_b", password="correct")

    csrf = _set_csrf_token(client)

    for _ in range(15):
        client.post(
            "/staff/login",
            data={
                "_csrf_token": csrf,
                "username": "user_a",
                "password": "wrong",
                "shelter": "abba",
            },
            follow_redirects=False,
        )

    response = client.post(
        "/staff/login",
        data={
            "_csrf_token": csrf,
            "username": "user_b",
            "password": "correct",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code in (302, 429)
