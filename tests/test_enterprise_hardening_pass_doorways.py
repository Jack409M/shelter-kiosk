from __future__ import annotations

from core.runtime import init_db


def _login_staff(client, *, role: str = "case_manager", shelter: str = "abba") -> None:
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = role
        session["shelter"] = shelter
        session["allowed_shelters"] = [shelter]


def _set_csrf(client) -> None:
    with client.session_transaction() as session:
        session["_csrf_token"] = "test"


def _seed_resident(db_execute, *, resident_id: int, shelter: str = "abba") -> None:
    db_execute("DELETE FROM residents WHERE id = %s", (resident_id,))
    db_execute(
        """
        INSERT INTO residents (id, first_name, last_name, shelter)
        VALUES (%s, %s, %s, %s)
        """,
        (resident_id, "Hardening", f"User{resident_id}", shelter),
    )


def _seed_pass(
    db_execute,
    *,
    pass_id: int,
    resident_id: int,
    shelter: str = "abba",
    status: str = "pending",
    pass_type: str = "pass",
    start_at: str | None = None,
    end_at: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    db_execute("DELETE FROM resident_pass_request_details WHERE pass_id = %s", (pass_id,))
    db_execute("DELETE FROM resident_notifications WHERE related_pass_id = %s", (pass_id,))
    db_execute("DELETE FROM resident_passes WHERE id = %s", (pass_id,))
    db_execute(
        """
        INSERT INTO resident_passes (
            id,
            resident_id,
            shelter,
            status,
            pass_type,
            start_at,
            end_at,
            start_date,
            end_date,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            pass_id,
            resident_id,
            shelter,
            status,
            pass_type,
            start_at,
            end_at,
            start_date,
            end_date,
            "2026-01-01T00:00:00",
            "2026-01-01T00:00:00",
        ),
    )
    db_execute(
        """
        INSERT INTO resident_pass_request_details (pass_id, created_at, updated_at)
        VALUES (%s, %s, %s)
        """,
        (pass_id, "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )


def test_legacy_get_pass_action_routes_do_not_change_state(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)

    with app.app_context():
        init_db()
        _seed_resident(db_execute, resident_id=710)
        _seed_pass(db_execute, pass_id=9710, resident_id=710, status="pending")
        _seed_pass(db_execute, pass_id=9711, resident_id=710, status="approved")

    approve_response = client.get("/staff/passes/approve/9710", follow_redirects=False)
    deny_response = client.get("/staff/passes/deny/9710", follow_redirects=False)
    check_in_response = client.get("/staff/passes/check-in/9711", follow_redirects=False)

    assert approve_response.status_code == 302
    assert deny_response.status_code == 302
    assert check_in_response.status_code == 302

    with app.app_context():
        pending_row = db_fetchone("SELECT status FROM resident_passes WHERE id = %s", (9710,))
        approved_row = db_fetchone("SELECT status FROM resident_passes WHERE id = %s", (9711,))
        attendance_count = db_fetchone(
            "SELECT COUNT(*) AS count FROM attendance_events WHERE resident_id = %s",
            (710,),
        )

        assert pending_row["status"] == "pending"
        assert approved_row["status"] == "approved"
        assert attendance_count["count"] == 0


def test_non_manager_staff_cannot_use_pass_doorways(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client, role="staff")
    _set_csrf(client)

    with app.app_context():
        init_db()
        _seed_resident(db_execute, resident_id=711)
        _seed_pass(db_execute, pass_id=9712, resident_id=711, status="pending")

    page_response = client.get("/staff/passes/pending", follow_redirects=False)
    action_response = client.post(
        "/staff/passes/9712/approve",
        data={"_csrf_token": "test"},
        follow_redirects=False,
    )

    assert page_response.status_code == 403
    assert action_response.status_code == 403

    with app.app_context():
        row = db_fetchone("SELECT status FROM resident_passes WHERE id = %s", (9712,))
        assert row["status"] == "pending"


def test_staff_cannot_approve_second_active_pass_for_same_resident(app, client):
    from core.db import db_execute, db_fetchone

    _login_staff(client)
    _set_csrf(client)

    with app.app_context():
        init_db()
        _seed_resident(db_execute, resident_id=712)
        _seed_pass(db_execute, pass_id=9713, resident_id=712, status="approved")
        _seed_pass(db_execute, pass_id=9714, resident_id=712, status="pending")
        db_execute(
            """
            DELETE FROM audit_log
            WHERE entity_type = 'pass'
              AND action_type = 'approve'
              AND action_details LIKE %s
            """,
            ("%pass_id=9714%",),
        )

    response = client.post(
        "/staff/passes/9714/approve",
        data={"_csrf_token": "test"},
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        pending_row = db_fetchone("SELECT status FROM resident_passes WHERE id = %s", (9714,))
        audit_count = db_fetchone(
            """
            SELECT COUNT(*) AS count
            FROM audit_log
            WHERE entity_type = 'pass'
              AND action_type = 'approve'
              AND action_details LIKE %s
            """,
            ("%pass_id=9714%",),
        )

        assert pending_row["status"] == "pending"
        assert audit_count["count"] == 0


def test_retention_expiry_only_closes_overdue_approved_passes(app):
    from core.db import db_execute, db_fetchone
    from core.pass_retention import expire_overdue_approved_passes_for_shelter

    with app.app_context():
        init_db()
        _seed_resident(db_execute, resident_id=713)
        _seed_resident(db_execute, resident_id=714)
        _seed_resident(db_execute, resident_id=715)

        _seed_pass(
            db_execute,
            pass_id=9715,
            resident_id=713,
            status="approved",
            start_at="2020-01-01T08:00:00",
            end_at="2020-01-01T10:00:00",
        )
        _seed_pass(
            db_execute,
            pass_id=9716,
            resident_id=714,
            status="pending",
            start_at="2020-01-01T08:00:00",
            end_at="2020-01-01T10:00:00",
        )
        _seed_pass(
            db_execute,
            pass_id=9717,
            resident_id=715,
            status="completed",
            start_at="2020-01-01T08:00:00",
            end_at="2020-01-01T10:00:00",
        )

        expired_count = expire_overdue_approved_passes_for_shelter("abba")

        approved_row = db_fetchone(
            "SELECT status, delete_after_at FROM resident_passes WHERE id = %s",
            (9715,),
        )
        pending_row = db_fetchone("SELECT status FROM resident_passes WHERE id = %s", (9716,))
        completed_row = db_fetchone("SELECT status FROM resident_passes WHERE id = %s", (9717,))

        assert expired_count >= 1
        assert approved_row["status"] == "expired"
        assert approved_row["delete_after_at"] is not None
        assert pending_row["status"] == "pending"
        assert completed_row["status"] == "completed"
