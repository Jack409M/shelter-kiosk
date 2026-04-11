from __future__ import annotations

from core.runtime import init_db


def _login_staff(client):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = "case_manager"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba", "haven"]


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _row_value(row, key: str, index: int):
    if isinstance(row, dict):
        return row[key]
    return row[index]


def test_transfer_moves_pending_and_approved_passes(app, client, monkeypatch):
    from core.db import db_execute, db_fetchall

    _login_staff(client)
    csrf = _set_csrf_token(client)

    with app.app_context():
        init_db()

        db_execute(
            """
            INSERT INTO residents (
                id,
                resident_identifier,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at
            )
            VALUES (1, 'abc123', 'Test', 'Resident', 'abba', TRUE, '2026-01-01')
            """
        )

        db_execute(
            """
            INSERT INTO resident_passes (
                id,
                resident_id,
                shelter,
                pass_type,
                status,
                created_at,
                updated_at
            )
            VALUES
                (1, 1, 'abba', 'pass', 'pending', '2026-01-01', '2026-01-01'),
                (2, 1, 'abba', 'pass', 'approved', '2026-01-01', '2026-01-01'),
                (3, 1, 'abba', 'pass', 'completed', '2026-01-01', '2026-01-01')
            """
        )

    monkeypatch.setattr(
        "routes.residents._upsert_resident_housing_assignment",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        "routes.residents._active_rent_config_for_resident",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        "routes.residents._availability_map_for_transfer",
        lambda: {"abba": [], "haven": [], "gratitude": []},
    )

    monkeypatch.setattr(
        "routes.residents.log_action",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        "core.residents.log_action",
        lambda *args, **kwargs: None,
    )

    response = client.post(
        "/staff/residents/1/transfer",
        data={
            "_csrf_token": csrf,
            "to_shelter": "haven",
            "note": "test transfer",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)

    with app.app_context():
        rows = db_fetchall(
            "SELECT id, shelter, status FROM resident_passes WHERE resident_id = 1 ORDER BY id"
        )

    results = {
        _row_value(row, "id", 0): (
            _row_value(row, "shelter", 1),
            _row_value(row, "status", 2),
        )
        for row in rows
    }

    assert results[1][0] == "haven"
    assert results[2][0] == "haven"
    assert results[3][0] == "abba"
