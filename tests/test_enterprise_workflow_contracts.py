from __future__ import annotations

import importlib
from pathlib import Path

from core.runtime import init_db


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CRITICAL_FILE_MIN_LINES = {
    "core/app_factory.py": 200,
    "core/db.py": 200,
    "core/intake_service.py": 250,
    "routes/case_management_parts/family.py": 500,
    "routes/case_management_parts/intake_income_support.py": 450,
    "routes/resident_detail.py": 200,
    "routes/resident_detail_parts/read.py": 200,
    "routes/resident_detail_parts/timeline.py": 350,
}

CRITICAL_ROUTES = {
    "/staff/login",
    "/staff/case-management",
    "/staff/case-management/intake-assessment/new",
    "/staff/case-management/<int:resident_id>/intake-edit",
    "/staff/case-management/<int:resident_id>/family-intake",
    "/staff/case-management/children/<int:child_id>/services",
    "/staff/case-management/children/<int:child_id>/edit",
    "/resident",
    "/resident/home",
    "/transport",
    "/pass-request",
    "/resident/portal",
    "/staff/passes/pending",
    "/staff/passes/<int:pass_id>/approve",
    "/staff/passes/<int:pass_id>/deny",
    "/staff/passes/<int:pass_id>/check-in",
}

CRITICAL_TABLE_COLUMNS = {
    "residents": {
        "id",
        "resident_identifier",
        "resident_code",
        "first_name",
        "last_name",
        "shelter",
        "is_active",
        "created_at",
        "updated_at",
    },
    "program_enrollments": {
        "id",
        "resident_id",
        "shelter",
        "entry_date",
        "exit_date",
        "program_status",
        "created_at",
        "updated_at",
    },
    "intake_assessments": {
        "id",
        "enrollment_id",
        "sobriety_date",
        "days_sober_at_entry",
        "created_at",
        "updated_at",
    },
    "family_snapshots": {
        "id",
        "enrollment_id",
        "kids_at_dwc",
        "created_at",
        "updated_at",
    },
    "resident_passes": {
        "id",
        "resident_id",
        "shelter",
        "pass_type",
        "status",
        "start_at",
        "end_at",
        "start_date",
        "end_date",
        "delete_after_at",
        "created_at",
        "updated_at",
    },
    "resident_pass_request_details": {
        "id",
        "pass_id",
        "resident_phone",
        "reviewed_by_user_id",
        "reviewed_at",
        "created_at",
        "updated_at",
    },
    "resident_children": {
        "id",
        "resident_id",
        "child_name",
        "birth_year",
        "is_active",
        "created_at",
        "updated_at",
    },
    "child_services": {
        "id",
        "resident_child_id",
        "enrollment_id",
        "service_date",
        "service_type",
        "is_deleted",
        "created_at",
        "updated_at",
    },
}


def _set_case_manager_session(client, *, shelter: str = "abba") -> None:
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "enterprise-contract-staff"
        session["role"] = "case_manager"
        session["shelter"] = shelter
        session["allowed_shelters"] = ["abba", "haven", "gratitude"]


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _insert_contract_resident(app, *, identifier: str = "enterprise_contract_resident") -> int:
    from core.db import db_execute, db_fetchone

    with app.app_context():
        init_db()
        db_execute(
            """
            DELETE FROM resident_notifications
            WHERE resident_id IN (SELECT id FROM residents WHERE resident_identifier = %s)
            """,
            (identifier,),
        )
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
            WHERE resident_id IN (SELECT id FROM residents WHERE resident_identifier = %s)
            """,
            (identifier,),
        )
        db_execute("DELETE FROM residents WHERE resident_identifier = %s", (identifier,))
        db_execute(
            """
            INSERT INTO residents (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                shelter,
                is_active,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                identifier,
                "EC000001",
                "Enterprise",
                "Contract",
                "abba",
                True,
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )
        row = db_fetchone(
            "SELECT id FROM residents WHERE resident_identifier = %s",
            (identifier,),
        )
        return int(row["id"])


def _insert_contract_pass(app, *, resident_id: int, status: str = "pending") -> int:
    from core.db import db_execute, db_fetchone

    with app.app_context():
        init_db()
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
                resident_id,
                "abba",
                "pass",
                status,
                "2099-01-01T10:00:00",
                "2099-01-01T18:00:00",
                "Enterprise Contract Test",
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )
        row = db_fetchone(
            """
            SELECT id
            FROM resident_passes
            WHERE resident_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (resident_id,),
        )
        pass_id = int(row["id"])
        db_execute(
            """
            INSERT INTO resident_pass_request_details (
                pass_id,
                resident_phone,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                pass_id,
                "8065550000",
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )
        return pass_id


def test_enterprise_critical_files_are_not_suspiciously_short() -> None:
    failures: list[str] = []

    for relative_path, minimum_lines in CRITICAL_FILE_MIN_LINES.items():
        path = PROJECT_ROOT / relative_path
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count < minimum_lines:
            failures.append(f"{relative_path}: {line_count} lines below floor {minimum_lines}")

    assert failures == []


def test_enterprise_critical_routes_remain_registered(app) -> None:
    registered = {rule.rule for rule in app.url_map.iter_rules()}
    missing = sorted(CRITICAL_ROUTES - registered)

    assert missing == []


def test_enterprise_critical_schema_columns_exist_after_startup(app) -> None:
    from core.db import db_fetchall

    missing: list[str] = []

    with app.app_context():
        init_db()
        for table, expected_columns in CRITICAL_TABLE_COLUMNS.items():
            rows = db_fetchall(f"PRAGMA table_info({table})")
            actual_columns = {row["name"] for row in rows}
            for column in sorted(expected_columns - actual_columns):
                missing.append(f"{table}.{column}")

    assert missing == []


def test_enterprise_recent_redesign_import_contracts() -> None:
    expected_symbols = {
        "core.intake_service": [
            "create_intake",
            "create_intake_for_existing_resident",
            "update_intake",
        ],
        "core.pass_retention": [
            "run_pass_retention_cleanup_for_shelter",
            "expire_overdue_approved_passes_for_shelter",
        ],
        "routes.case_management_parts.family": [
            "family_intake_view",
            "edit_child_view",
            "delete_child_view",
            "child_services_view",
        ],
        "routes.case_management_parts.intake_income_support": [
            "load_intake_income_support",
            "upsert_intake_income_support",
            "recalculate_intake_income_support",
        ],
        "routes.resident_detail_parts.timeline": [
            "load_timeline",
            "build_calendar_context",
        ],
    }

    missing: list[str] = []

    for module_name, symbols in expected_symbols.items():
        module = importlib.import_module(module_name)
        for symbol in symbols:
            if not hasattr(module, symbol):
                missing.append(f"{module_name}.{symbol}")

    assert missing == []


def test_enterprise_pass_state_cannot_change_through_get_routes(app, client) -> None:
    from core.db import db_fetchone

    _set_case_manager_session(client)
    resident_id = _insert_contract_resident(app)
    pass_id = _insert_contract_pass(app, resident_id=resident_id, status="pending")

    client.get(f"/staff/passes/approve/{pass_id}")
    client.get(f"/staff/passes/deny/{pass_id}")
    client.get(f"/staff/passes/check-in/{pass_id}")

    with app.app_context():
        row = db_fetchone(
            "SELECT status, approved_by, approved_at FROM resident_passes WHERE id = %s",
            (pass_id,),
        )

    assert row["status"] == "pending"
    assert row["approved_by"] is None
    assert row["approved_at"] is None


def test_enterprise_pass_approval_contract_creates_notification(app, client, monkeypatch) -> None:
    import routes.attendance_parts.pass_actions as actions_module
    from core.db import db_fetchone

    _set_case_manager_session(client)
    csrf_token = _set_csrf_token(client)
    resident_id = _insert_contract_resident(app, identifier="enterprise_contract_pass_approve")
    pass_id = _insert_contract_pass(app, resident_id=resident_id, status="pending")

    monkeypatch.setattr(actions_module, "send_sms", lambda *args, **kwargs: None)
    monkeypatch.setattr(actions_module, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        f"/staff/passes/{pass_id}/approve",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)

    with app.app_context():
        pass_row = db_fetchone(
            "SELECT status, approved_by, approved_at FROM resident_passes WHERE id = %s",
            (pass_id,),
        )
        notification_row = db_fetchone(
            """
            SELECT notification_type, related_pass_id
            FROM resident_notifications
            WHERE resident_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (resident_id,),
        )

    assert pass_row["status"] == "approved"
    assert pass_row["approved_by"] == 1
    assert pass_row["approved_at"]
    assert notification_row["notification_type"] == "pass_approved"
    assert notification_row["related_pass_id"] == pass_id


def test_enterprise_transfer_keeps_pending_passes_with_resident(app, client, monkeypatch) -> None:
    from core.db import db_execute, db_fetchall, db_fetchone

    _set_case_manager_session(client)
    csrf_token = _set_csrf_token(client)
    resident_id = _insert_contract_resident(app, identifier="enterprise_contract_transfer")
    pass_id = _insert_contract_pass(app, resident_id=resident_id, status="pending")

    monkeypatch.setattr(
        "routes.residents.get_all_shelters",
        lambda: ["abba", "haven", "gratitude"],
    )

    response = client.post(
        f"/staff/residents/{resident_id}/transfer",
        data={
            "_csrf_token": csrf_token,
            "to_shelter": "haven",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)

    with app.app_context():
        resident = db_fetchone(
            "SELECT shelter FROM residents WHERE id = %s",
            (resident_id,),
        )
        pass_rows = db_fetchall(
            "SELECT id, shelter, status FROM resident_passes WHERE resident_id = %s",
            (resident_id,),
        )
        db_execute("DELETE FROM resident_pass_request_details WHERE pass_id = %s", (pass_id,))
        db_execute("DELETE FROM resident_passes WHERE id = %s", (pass_id,))

    assert resident["shelter"] == "haven"
    assert pass_rows
    assert all(row["shelter"] == "haven" for row in pass_rows)
    assert all(row["status"] == "pending" for row in pass_rows)
