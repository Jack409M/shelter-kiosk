from __future__ import annotations

import logging


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _set_case_manager_session(client) -> None:
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "case_manager"
        session["role"] = "case_manager"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]


def _disable_admin_only_mode(monkeypatch) -> None:
    import core.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "db_fetchone",
        lambda *args, **kwargs: {"admin_login_only_mode": False},
    )


def test_followup_save_failure_logs_and_renders_form(client, monkeypatch, caplog):
    import routes.case_management_parts.followups as followups_module

    _disable_admin_only_mode(monkeypatch)
    _set_case_manager_session(client)
    csrf_token = _set_csrf_token(client)

    monkeypatch.setattr(followups_module, "init_db", lambda: None)
    monkeypatch.setattr(
        followups_module,
        "_fetch_resident_and_enrollment",
        lambda resident_id: ({"id": resident_id, "first_name": "Jane"}, {"id": 7}),
    )
    monkeypatch.setattr(
        followups_module,
        "validate_followup_form",
        lambda form, followup_type: (
            {
                "followup_date": "2026-04-16",
                "followup_type": followup_type,
                "income_at_followup": 1200.0,
                "sober_at_followup": "yes",
                "notes": "ok",
            },
            [],
        ),
    )
    monkeypatch.setattr(
        followups_module,
        "_upsert_followup",
        lambda enrollment_id, data: (_ for _ in ()).throw(RuntimeError("db fail")),
    )
    monkeypatch.setattr(followups_module, "render_template", lambda *args, **kwargs: "form")

    with caplog.at_level(logging.ERROR):
        response = client.post(
            "/staff/case-management/1/followup/6_month",
            data={"_csrf_token": csrf_token},
        )

    assert response.status_code == 200
    assert response.data == b"form"
    messages = [record.getMessage() for record in caplog.records]
    assert any("followup_save_failed" in message for message in messages)


def test_income_support_post_failure_logs_and_renders_page(client, monkeypatch, caplog):
    import routes.case_management_parts.income_support as income_support_module

    _disable_admin_only_mode(monkeypatch)
    _set_case_manager_session(client)
    csrf_token = _set_csrf_token(client)

    resident = {
        "id": 1,
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
    }
    values = {
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
    }

    monkeypatch.setattr(income_support_module, "init_db", lambda: None)
    monkeypatch.setattr(income_support_module, "_load_resident_in_scope", lambda resident_id, shelter: resident)
    monkeypatch.setattr(income_support_module, "_load_current_enrollment", lambda resident_id, shelter: {"id": 7})
    monkeypatch.setattr(income_support_module, "validate_income_support_form", lambda form: (values, []))
    monkeypatch.setattr(
        income_support_module,
        "upsert_intake_income_support",
        lambda enrollment_id, values: (_ for _ in ()).throw(RuntimeError("db fail")),
    )
    monkeypatch.setattr(income_support_module, "load_intake_income_support", lambda enrollment_id: {})
    monkeypatch.setattr(income_support_module, "render_template", lambda *args, **kwargs: "income")

    with caplog.at_level(logging.ERROR):
        response = client.post(
            "/staff/case-management/1/income-support",
            data={"_csrf_token": csrf_token},
        )

    assert response.status_code == 200
    assert response.data == b"income"
    messages = [record.getMessage() for record in caplog.records]
    assert any("income_support_save_failed" in message for message in messages)


def test_income_support_get_resync_failure_logs_and_renders_page(client, monkeypatch, caplog):
    import routes.case_management_parts.income_support as income_support_module

    _disable_admin_only_mode(monkeypatch)
    _set_case_manager_session(client)

    resident = {
        "id": 1,
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
    }

    monkeypatch.setattr(income_support_module, "init_db", lambda: None)
    monkeypatch.setattr(income_support_module, "_load_resident_in_scope", lambda resident_id, shelter: resident)
    monkeypatch.setattr(income_support_module, "_load_current_enrollment", lambda resident_id, shelter: {"id": 7})
    monkeypatch.setattr(
        income_support_module,
        "recalculate_intake_income_support",
        lambda enrollment_id: (_ for _ in ()).throw(RuntimeError("recalc fail")),
    )
    monkeypatch.setattr(income_support_module, "load_intake_income_support", lambda enrollment_id: {})
    monkeypatch.setattr(income_support_module, "render_template", lambda *args, **kwargs: "income")

    with caplog.at_level(logging.ERROR):
        response = client.get("/staff/case-management/1/income-support")

    assert response.status_code == 200
    assert response.data == b"income"
    messages = [record.getMessage() for record in caplog.records]
    assert any("income_support_resync_failed" in message for message in messages)


def test_budget_session_add_failure_logs_and_redirects(client, monkeypatch, caplog):
    import routes.case_management_parts.budget_sessions as budget_sessions_module

    _disable_admin_only_mode(monkeypatch)
    _set_case_manager_session(client)
    csrf_token = _set_csrf_token(client)

    monkeypatch.setattr(budget_sessions_module, "init_db", lambda: None)
    monkeypatch.setattr(
        budget_sessions_module,
        "_resident_context",
        lambda resident_id: {"id": resident_id, "enrollment_id": 7},
    )
    monkeypatch.setattr(
        budget_sessions_module,
        "validate_budget_session_form",
        lambda form: ({"session_date": "2026-04-16", "notes": "note"}, []),
    )
    monkeypatch.setattr(
        budget_sessions_module,
        "db_execute",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("insert fail")),
    )

    with caplog.at_level(logging.ERROR):
        response = client.post(
            "/staff/case-management/1/budget-sessions",
            data={"_csrf_token": csrf_token},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "/staff/case-management/1/budget-sessions" in response.headers["Location"]
    messages = [record.getMessage() for record in caplog.records]
    assert any("budget_session_add_failed" in message for message in messages)


def test_budget_session_edit_failure_logs_and_redirects(client, monkeypatch, caplog):
    import routes.case_management_parts.budget_sessions as budget_sessions_module

    _disable_admin_only_mode(monkeypatch)
    _set_case_manager_session(client)
    csrf_token = _set_csrf_token(client)

    monkeypatch.setattr(budget_sessions_module, "init_db", lambda: None)
    monkeypatch.setattr(
        budget_sessions_module,
        "_resident_context",
        lambda resident_id: {"id": resident_id, "enrollment_id": 7},
    )
    monkeypatch.setattr(
        budget_sessions_module,
        "db_fetchone",
        lambda *args, **kwargs: {"id": 9, "resident_id": 1, "session_date": "2026-04-16", "notes": "x"},
    )
    monkeypatch.setattr(
        budget_sessions_module,
        "validate_budget_session_form",
        lambda form: ({"session_date": "2026-04-16", "notes": "note"}, []),
    )
    monkeypatch.setattr(
        budget_sessions_module,
        "db_execute",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("update fail")),
    )

    with caplog.at_level(logging.ERROR):
        response = client.post(
            "/staff/case-management/1/budget-sessions/9/edit",
            data={"_csrf_token": csrf_token},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "/staff/case-management/1/budget-sessions/9/edit" in response.headers["Location"]
    messages = [record.getMessage() for record in caplog.records]
    assert any("budget_session_edit_failed" in message for message in messages)
