from __future__ import annotations

import time

from core.runtime import init_db


def _login_staff(client, *, role: str = "case_manager", shelter: str = "abba") -> None:
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = role
        session["shelter"] = shelter
        session["allowed_shelters"] = [shelter]


def _seed_pass_queue(app, *, count: int, shelter: str = "abba") -> None:
    from core.db import db_execute

    with app.app_context():
        init_db()

        for i in range(count):
            identifier = f"perf_pass_resident_{i}"
            code = f"66{i:05d}"

            db_execute(
                """
                DELETE FROM resident_pass_request_details
                WHERE pass_id IN (
                    SELECT rp.id
                    FROM resident_passes rp
                    JOIN residents r ON r.id = rp.resident_id
                    WHERE r.resident_identifier = %s
                )
                """,
                (identifier,),
            )
            db_execute(
                """
                DELETE FROM resident_passes
                WHERE resident_id IN (
                    SELECT id FROM residents WHERE resident_identifier = %s
                )
                """,
                (identifier,),
            )
            db_execute(
                """
                DELETE FROM residents
                WHERE resident_identifier = %s
                   OR resident_code = %s
                """,
                (identifier, code),
            )

            db_execute(
                """
                INSERT INTO residents (
                    resident_identifier,
                    resident_code,
                    first_name,
                    last_name,
                    shelter,
                    program_level,
                    is_active,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    identifier,
                    code,
                    "Perf",
                    f"Resident{i}",
                    shelter,
                    "5",
                    True,
                    "2026-01-01T00:00:00",
                ),
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
                SELECT
                    id,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                FROM residents
                WHERE resident_identifier = %s
                """,
                (
                    shelter,
                    "pass",
                    "pending",
                    "2099-01-01T10:00:00",
                    "2099-01-01T18:00:00",
                    "Clinic",
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                    identifier,
                ),
            )


def _seed_resident_list(app, *, count: int, shelter: str = "abba") -> None:
    from core.db import db_execute

    with app.app_context():
        init_db()

        for i in range(count):
            identifier = f"perf_list_resident_{i}"
            code = f"55{i:05d}"

            db_execute(
                """
                DELETE FROM residents
                WHERE resident_identifier = %s
                   OR resident_code = %s
                """,
                (identifier, code),
            )

            db_execute(
                """
                INSERT INTO residents (
                    resident_identifier,
                    resident_code,
                    first_name,
                    last_name,
                    shelter,
                    program_level,
                    is_active,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    identifier,
                    code,
                    "Load",
                    f"Resident{i}",
                    shelter,
                    "5",
                    True,
                    "2026-01-01T00:00:00",
                ),
            )


def test_staff_passes_pending_page_handles_queue_volume(app, client):
    _seed_pass_queue(app, count=150, shelter="abba")
    _login_staff(client, role="case_manager", shelter="abba")

    started = time.perf_counter()
    response = client.get("/staff/passes/pending", follow_redirects=False)
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed < 5.0


def test_staff_residents_page_handles_list_volume(app, client):
    _seed_resident_list(app, count=250, shelter="abba")
    _login_staff(client, role="case_manager", shelter="abba")

    started = time.perf_counter()
    response = client.get("/staff/residents", follow_redirects=False)
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed < 5.0
