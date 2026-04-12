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


# -----------------------------------------
# SECURITY
# -----------------------------------------

def test_transfer_requires_login(client):
    response = client.post(
        "/staff/residents/1/transfer",
        data={},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)


# -----------------------------------------
# INVALID INPUT
# -----------------------------------------

def test_transfer_rejects_invalid_shelter(app, client, monkeypatch):
    from core.db import db_execute, db_fetchone

    _login_staff(client)
    csrf = _set_csrf_token(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM residents WHERE resident_identifier = %s", ("t_invalid",))

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
            ("t_invalid", "1111", "Test", "Invalid", "abba", True, "2026-01-01"),
        )

        resident = db_fetchone(
            "SELECT id, shelter FROM residents WHERE resident_identifier = %s",
            ("t_invalid",),
        )

    monkeypatch.setattr(
        "routes.residents.get_all_shelters",
        lambda: ["abba", "haven", "gratitude"],
    )

    client.post(
        f"/staff/residents/{resident['id']}/transfer",
        data={
            "_csrf_token": csrf,
            "to_shelter": "fake",
        },
        follow_redirects=False,
    )

    # 🔴 REAL ASSERT: shelter should NOT change
    with app.app_context():
        updated = db_fetchone(
            "SELECT shelter FROM residents WHERE id = %s",
            (resident["id"],),
        )

    assert updated["shelter"] == "abba"


# -----------------------------------------
# NO-OP TRANSFER
# -----------------------------------------

def test_transfer_same_shelter_no_change(app, client, monkeypatch):
    from core.db import db_execute, db_fetchone

    _login_staff(client)
    csrf = _set_csrf_token(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM residents WHERE resident_identifier = %s", ("t_same",))

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
            ("t_same", "2222", "Same", "Shelter", "abba", True, "2026-01-01"),
        )

        resident = db_fetchone(
            "SELECT id, shelter FROM residents WHERE resident_identifier = %s",
            ("t_same",),
        )

    monkeypatch.setattr(
        "routes.residents.get_all_shelters",
        lambda: ["abba", "haven", "gratitude"],
    )

    client.post(
        f"/staff/residents/{resident['id']}/transfer",
        data={
            "_csrf_token": csrf,
            "to_shelter": "abba",
        },
        follow_redirects=False,
    )

    # 🔴 REAL ASSERT: still same shelter
    with app.app_context():
        updated = db_fetchone(
            "SELECT shelter FROM residents WHERE id = %s",
            (resident["id"],),
        )

    assert updated["shelter"] == "abba"


# -----------------------------------------
# REAL TRANSFER
# -----------------------------------------

def test_transfer_updates_resident_and_related_records(app, client, monkeypatch):
    from core.db import db_execute, db_fetchone, db_fetchall

    _login_staff(client)
    csrf = _set_csrf_token(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM residents WHERE resident_identifier = %s", ("t_real",))

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
            ("t_real", "3333", "Real", "Transfer", "abba", True, "2026-01-01"),
        )

        resident = db_fetchone(
            "SELECT id, resident_identifier FROM residents WHERE resident_identifier = %s",
            ("t_real",),
        )

        # create dependent records
        db_execute(
            """
            INSERT INTO leave_requests (resident_identifier, shelter, status)
            VALUES (%s, %s, %s)
            """,
            (resident["resident_identifier"], "abba", "pending"),
        )

        db_execute(
            """
            INSERT INTO transport_requests (resident_identifier, shelter, status)
            VALUES (%s, %s, %s)
            """,
            (resident["resident_identifier"], "abba", "pending"),
        )

    monkeypatch.setattr(
        "routes.residents.get_all_shelters",
        lambda: ["abba", "haven", "gratitude"],
    )

    client.post(
        f"/staff/residents/{resident['id']}/transfer",
        data={
            "_csrf_token": csrf,
            "to_shelter": "haven",
        },
        follow_redirects=False,
    )

    # 🔴 ASSERT 1: resident moved
    with app.app_context():
        updated = db_fetchone(
            "SELECT shelter FROM residents WHERE id = %s",
            (resident["id"],),
        )

        assert updated["shelter"] == "haven"

        # 🔴 ASSERT 2: related records updated
        leave = db_fetchall(
            "SELECT shelter FROM leave_requests WHERE resident_identifier = %s",
            (resident["resident_identifier"],),
        )

        transport = db_fetchall(
            "SELECT shelter FROM transport_requests WHERE resident_identifier = %s",
            (resident["resident_identifier"],),
        )

    assert all(r["shelter"] == "haven" for r in leave)
    assert all(r["shelter"] == "haven" for r in transport)
