from __future__ import annotations

from core.runtime import init_db


def _login_staff(client, *, role: str = "case_manager", shelter: str = "abba") -> None:
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = role
        session["shelter"] = shelter
        session["allowed_shelters"] = ["abba", "haven", "gratitude"]


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def test_staff_residents_requires_login_redirects(client):
    response = client.get("/staff/residents", follow_redirects=False)

    assert response.status_code in (301, 302)


def test_staff_residents_page_loads_for_staff(app, client):
    from core.db import db_execute

    _login_staff(client, role="staff", shelter="abba")

    with app.app_context():
        init_db()

        db_execute(
            """
            DELETE FROM residents
            WHERE resident_identifier = %s
            """,
            ("test_staff_residents_page_loads",),
        )

        db_execute(
            """
            SELECT setval(
                pg_get_serial_sequence('residents', 'id'),
                COALESCE((SELECT MAX(id) FROM residents), 1),
                true
            )
            """
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
                "test_staff_residents_page_loads",
                "12345678",
                "Jane",
                "Resident",
                "abba",
                True,
                "2026-01-01",
            ),
        )

    response = client.get("/staff/residents", follow_redirects=False)

    assert response.status_code == 200
    assert b"Jane" in response.data
    assert b"Resident" in response.data


def test_staff_resident_transfer_invalid_shelter_redirects_with_error(app, client, monkeypatch):
    from core.db import db_execute, db_fetchone

    _login_staff(client, role="case_manager", shelter="abba")
    csrf = _set_csrf_token(client)

    with app.app_context():
        init_db()

        db_execute(
            """
            DELETE FROM residents
            WHERE resident_identifier = %s
            """,
            ("test_transfer_invalid_shelter",),
        )

        db_execute(
            """
            SELECT setval(
                pg_get_serial_sequence('residents', 'id'),
                COALESCE((SELECT MAX(id) FROM residents), 1),
                true
            )
            """
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
                "test_transfer_invalid_shelter",
                "87654321",
                "Transfer",
                "Test",
                "abba",
                True,
                "2026-01-01",
            ),
        )

        resident = db_fetchone(
            """
            SELECT id
            FROM residents
            WHERE resident_identifier = %s
            """,
            ("test_transfer_invalid_shelter",),
        )
        resident_id = resident["id"]

    monkeypatch.setattr(
        "routes.residents.get_all_shelters",
        lambda: ["abba", "haven", "gratitude"],
    )
    monkeypatch.setattr(
        "routes.residents._availability_map_for_transfer",
        lambda: {"abba": [], "haven": [], "gratitude": []},
    )

    response = client.post(
        f"/staff/residents/{resident_id}/transfer",
        data={
            "_csrf_token": csrf,
            "to_shelter": "not-a-real-shelter",
            "note": "bad transfer",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)


def test_staff_resident_transfer_same_shelter_without_change_redirects(app, client, monkeypatch):
    from core.db import db_execute, db_fetchone

    _login_staff(client, role="case_manager", shelter="abba")
    csrf = _set_csrf_token(client)

    with app.app_context():
        init_db()

        db_execute(
            """
            DELETE FROM residents
            WHERE resident_identifier = %s
            """,
            ("test_transfer_same_shelter",),
        )

        db_execute(
            """
            SELECT setval(
                pg_get_serial_sequence('residents', 'id'),
                COALESCE((SELECT MAX(id) FROM residents), 1),
                true
            )
            """
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
                "test_transfer_same_shelter",
                "11223344",
                "Same",
                "Shelter",
                "abba",
                True,
                "2026-01-01",
            ),
        )

        resident = db_fetchone(
            """
            SELECT id
            FROM residents
            WHERE resident_identifier = %s
            """,
            ("test_transfer_same_shelter",),
        )
        resident_id = resident["id"]

    monkeypatch.setattr(
        "routes.residents.get_all_shelters",
        lambda: ["abba", "haven", "gratitude"],
    )
    monkeypatch.setattr(
        "routes.residents._availability_map_for_transfer",
        lambda: {"abba": ["A1"], "haven": [], "gratitude": []},
    )
    monkeypatch.setattr(
        "routes.residents._active_rent_config_for_resident",
        lambda resident_id, shelter: {
            "id": 1,
            "apartment_number_snapshot": "A1",
            "apartment_size_snapshot": "1 bedroom",
        },
    )

    response = client.post(
        f"/staff/residents/{resident_id}/transfer",
        data={
            "_csrf_token": csrf,
            "to_shelter": "abba",
            "apartment_number": "A1",
            "note": "no change",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
