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


# ----------------------------
# Residents page
# ----------------------------

def test_staff_residents_requires_login_redirects(client):
    response = client.get("/staff/residents", follow_redirects=False)
    assert response.status_code in (301, 302)


def test_staff_residents_page_loads_for_staff(app, client):
    from core.db import db_execute

    _login_staff(client, role="staff", shelter="abba")

    with app.app_context():
        init_db()

        db_execute("DELETE FROM residents WHERE resident_identifier = %s",
                   ("test_staff_residents_page_loads",))

        db_execute("""
            INSERT INTO residents (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (
            "test_staff_residents_page_loads",
            "12345678",
            "Jane",
            "Resident",
            "abba",
            True,
        ))

    response = client.get("/staff/residents", follow_redirects=False)

    assert response.status_code == 200
    assert b"Jane" in response.data
    assert b"Resident" in response.data


# ----------------------------
# Transfer validation
# ----------------------------

def test_transfer_invalid_shelter_redirects(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)
    csrf = _set_csrf_token(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM residents WHERE resident_identifier = %s",
                   ("test_transfer_invalid",))

        db_execute("""
            INSERT INTO residents (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (
            "test_transfer_invalid",
            "11111111",
            "Bad",
            "Shelter",
            "abba",
            True,
        ))

        resident_id = db_fetchone(
            "SELECT id FROM residents WHERE resident_identifier = %s",
            ("test_transfer_invalid",),
        )["id"]

    response = client.post(
        f"/staff/residents/{resident_id}/transfer",
        data={
            "_csrf_token": csrf,
            "to_shelter": "not-real",
            "note": "invalid",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)


def test_transfer_same_shelter_no_change_redirects(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)
    csrf = _set_csrf_token(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM residents WHERE resident_identifier = %s",
                   ("test_transfer_same",))

        db_execute("""
            INSERT INTO residents (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (
            "test_transfer_same",
            "22222222",
            "Same",
            "Shelter",
            "abba",
            True,
        ))

        resident_id = db_fetchone(
            "SELECT id FROM residents WHERE resident_identifier = %s",
            ("test_transfer_same",),
        )["id"]

    response = client.post(
        f"/staff/residents/{resident_id}/transfer",
        data={
            "_csrf_token": csrf,
            "to_shelter": "abba",
            "note": "no change",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)


# ----------------------------
# Successful transfer (real behavior)
# ----------------------------

def test_transfer_updates_resident_shelter(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)
    csrf = _set_csrf_token(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM residents WHERE resident_identifier = %s",
                   ("test_transfer_success",))

        db_execute("""
            INSERT INTO residents (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (
            "test_transfer_success",
            "33333333",
            "Move",
            "Resident",
            "abba",
            True,
        ))

        resident_id = db_fetchone(
            "SELECT id FROM residents WHERE resident_identifier = %s",
            ("test_transfer_success",),
        )["id"]

    response = client.post(
        f"/staff/residents/{resident_id}/transfer",
        data={
            "_csrf_token": csrf,
            "to_shelter": "haven",
            "note": "transfer",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)

    with app.app_context():
        updated = db_fetchone(
            "SELECT shelter FROM residents WHERE id = %s",
            (resident_id,),
        )

        assert updated["shelter"] == "haven"


