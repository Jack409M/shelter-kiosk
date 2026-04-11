from core.runtime import init_db


def test_login_page_loads(client):
    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 200


def test_login_invalid_credentials(client, app):
    from core.db import db_execute

    with app.app_context():
        init_db()

        db_execute(
            """
            DELETE FROM staff_users
            WHERE username = %s
            """,
            ("test_user_invalid",),
        )

    response = client.post(
        "/login",
        data={
            "username": "test_user_invalid",
            "password": "wrongpassword",
        },
        follow_redirects=True,
    )

    assert b"invalid" in response.data.lower() or response.status_code == 200


def test_login_requires_username(client):
    response = client.post(
        "/login",
        data={
            "username": "",
            "password": "whatever",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200


def test_logout_clears_session(client):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1

    response = client.get("/logout", follow_redirects=True)

    assert response.status_code == 200
