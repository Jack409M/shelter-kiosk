from __future__ import annotations

import sqlite3

import pytest

from core.runtime import init_db

TEST_TIMESTAMP = "2026-01-01T00:00:00"


def _login_staff(client, *, role: str = "case_manager", shelter: str = "abba") -> None:
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = role
        session["shelter"] = shelter
        session["allowed_shelters"] = [shelter]


def _seed_resident(db_execute, *, resident_id: int, shelter: str = "abba") -> None:
    db_execute("DELETE FROM residents WHERE id = %s", (resident_id,))
    db_execute(
        "INSERT INTO residents (id, first_name, last_name, shelter, created_at) VALUES (%s, %s, %s, %s, %s)",
        (resident_id, "Hardening", f"User{resident_id}", shelter, TEST_TIMESTAMP),
    )


def _seed_pass(
    db_execute, *, pass_id: int, resident_id: int, shelter: str = "abba", status: str = "pending"
):
    db_execute("DELETE FROM resident_passes WHERE id = %s", (pass_id,))
    db_execute(
        "INSERT INTO resident_passes (id, resident_id, shelter, status, pass_type, created_at, updated_at) VALUES (%s,%s,%s,%s,'pass','2026-01-01','2026-01-01')",
        (pass_id, resident_id, shelter, status),
    )


def test_database_rejects_second_active_pass_for_same_resident(app):
    from core.db import db_execute

    with app.app_context():
        init_db()
        _seed_resident(db_execute, resident_id=900)
        _seed_pass(db_execute, pass_id=9900, resident_id=900, status="approved")

        with pytest.raises(sqlite3.IntegrityError):
            _seed_pass(db_execute, pass_id=9901, resident_id=900, status="pending")
