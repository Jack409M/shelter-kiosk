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

    with app.app_context():
        updated = db_fetchone(
            "SELECT shelter FROM residents WHERE id = %s",
            (resident["id"],),
        )

    assert updated["shelter"] == "abba"


# -----------------------------------------
# NO OP TRANSFER
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
    from core.db import db_execute, db_fetchall, db_fetchone

    _login_staff(client)
    csrf = _set_csrf_token(client)

    with app.app_context():
        init_db()

        db_execute("DELETE FROM resident_pass_request_details WHERE pass_id IN (SELECT id FROM resident_passes WHERE resident_id IN (SELECT id FROM residents WHERE resident_identifier = %s))", ("t_real",))
        db_execute("DELETE FROM resident_passes WHERE resident_id IN (SELECT id FROM residents WHERE resident_identifier = %s)", ("t_real",))
        db_execute("DELETE FROM transport_requests WHERE resident_identifier = %s", ("t_real",))
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

        db_execute(
            """
            INSERT INTO resident_passes (
                resident_id,
                shelter,
                pass_type,
                status,
                start_at,
                end_at,
                destination,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resident["id"],
                "abba",
                "pass",
                "pending",
                "2099-01-01T10:00:00",
                "2099-01-01T18:00:00",
                "Clinic",
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )

        db_execute(
            """
            INSERT INTO transport_requests (
                resident_identifier,
                shelter,
                first_name,
                last_name,
                needed_at,
                pickup_location,
                destination,
                status,
                submitted_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resident["resident_identifier"],
                "abba",
                "Real",
                "Transfer",
                "2099-01-01T09:00:00",
                "DWC",
                "Clinic",
                "pending",
                "2026-01-01T00:00:00",
            ),
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

    with app.app_context():
        updated = db_fetchone(
            "SELECT shelter FROM residents WHERE id = %s",
            (resident["id"],),
        )

        passes = db_fetchall(
            "SELECT shelter FROM resident_passes WHERE resident_id = %s",
            (resident["id"],),
        )

        transport = db_fetchall(
            "SELECT shelter FROM transport_requests WHERE resident_identifier = %s",
            (resident["resident_identifier"],),
        )

    assert updated["shelter"] == "haven"
    assert all(r["shelter"] == "haven" for r in passes)
    assert all(r["shelter"] == "haven" for r in transport)
