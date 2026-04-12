from core.runtime import init_db


def _login_resident(client):
    with client.session_transaction() as session:
        session["resident_user_id"] = 1
        session["resident_identifier"] = "test_resident"


def _set_csrf(client):
    with client.session_transaction() as session:
        session["_csrf_token"] = "test-csrf"
    return "test-csrf"


def test_resident_requests_requires_login(client):
    response = client.get("/resident/requests", follow_redirects=False)

    assert response.status_code in (301, 302)


def test_resident_requests_page_loads(app, client):
    from core.db import db_execute

    _login_resident(client)

    with app.app_context():
        init_db()

        db_execute(
            """
            DELETE FROM residents WHERE resident_identifier = %s
            """,
            ("test_resident",),
        )

        db_execute(
            """
            INSERT INTO residents (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "test_resident",
                "11111111",
                "Res",
                "User",
                "abba",
                True,
                "2026-01-01",
            ),
        )

    response = client.get("/resident/requests", follow_redirects=False)

    assert response.status_code == 200


def test_resident_requests_post_requires_csrf(app, client):
    _login_resident(client)

    response = client.post(
        "/resident/requests",
        data={"request_type": "test"},
        follow_redirects=False,
    )

    assert response.status_code in (400, 403)


def test_resident_requests_post_basic(app, client):
    from core.db import db_execute

    _login_resident(client)
    csrf = _set_csrf(client)

    with app.app_context():
        init_db()

        db_execute(
            "DELETE FROM residents WHERE resident_identifier = %s",
            ("test_resident",),
        )

        db_execute(
            """
            INSERT INTO residents (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "test_resident",
                "22222222",
                "Res",
                "User",
                "abba",
                True,
                "2026-01-01",
            ),
        )

    response = client.post(
        "/resident/requests",
        data={
            "_csrf_token": csrf,
            "request_type": "general",
            "note": "test request",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
