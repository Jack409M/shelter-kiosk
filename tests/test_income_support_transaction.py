from __future__ import annotations

from core.db import db_fetchone


def test_income_support_atomic_rollback(client, monkeypatch):
    import routes.case_management_parts.income_support as income_support_module

    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "case_manager"
        session["role"] = "case_manager"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]
        session["_csrf_token"] = "test-csrf"

    import core.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "db_fetchone",
        lambda *args, **kwargs: {"admin_login_only_mode": False},
    )

    monkeypatch.setattr(
        income_support_module,
        "_load_resident_in_scope",
        lambda resident_id, shelter: {"id": resident_id},
    )
    monkeypatch.setattr(
        income_support_module,
        "_load_current_enrollment",
        lambda resident_id, shelter: {"id": 999},
    )

    monkeypatch.setattr(
        income_support_module,
        "validate_income_support_form",
        lambda form: (
            {
                "employment_status_current": "employed",
                "employer_name": "ACME",
                "employment_type_current": "full_time",
                "supervisor_name": None,
                "supervisor_phone": None,
                "unemployment_reason": None,
                "employment_notes": None,
                "current_job_start_date": None,
                "previous_job_end_date": None,
                "upward_job_change": None,
                "job_change_notes": None,
            },
            [],
        ),
    )

    monkeypatch.setattr(
        income_support_module,
        "_sync_resident_income_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced failure")),
    )

    client.post(
        "/staff/case-management/1/income-support",
        data={"_csrf_token": "test-csrf"},
    )

    with client.application.app_context():
        row = db_fetchone(
            "SELECT * FROM intake_income_supports WHERE enrollment_id = ?",
            (999,),
        )

    assert row is None, "Transaction should have rolled back but data was committed"
