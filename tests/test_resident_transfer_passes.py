from __future__ import annotations


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


def test_transfer_moves_pending_and_approved_passes(app, client, monkeypatch):
    from core.db import db_execute, db_fetchall

    _login_staff(client)
    csrf = _set_csrf_token(client)

    # Create resident
    db_execute(
        """
        INSERT INTO residents (id, resident_identifier, first_name, last_name, shelter, is_active, created_at)
        VALUES (1, 'abc123', 'Test', 'Resident', 'abba', 1, '2026-01-01')
        """
    )

    # Create passes: pending, approved, completed
    db_execute(
        """
        INSERT INTO resident_passes (id, resident_id, shelter, status, created_at)
        VALUES
            (1, 1, 'abba', 'pending', '2026-01-01'),
            (2, 1, 'abba', 'approved', '2026-01-01'),
            (3, 1, 'abba', 'completed', '2026-01-01')
        """
    )

    # Monkeypatch housing + rent stuff to avoid side effects
    import routes.residents as residents_module
    monkeypatch.setattr(residents_module, "_upsert_resident_housing_assignment", lambda **kwargs: None)

    # Execute transfer
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

    rows = db_fetchall(
        "SELECT id, shelter, status FROM resident_passes WHERE resident_id = 1 ORDER BY id"
    )

    results = {row[0]: (row[1], row[2]) for row in rows}

    # Pending moved
    assert results[1][0] == "haven"

    # Approved moved
    assert results[2][0] == "haven"

    # Completed stayed
    assert results[3][0] == "abba"
