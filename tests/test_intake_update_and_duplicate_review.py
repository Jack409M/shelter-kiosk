from __future__ import annotations

from core.intake_service import IntakeReviewResult


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


def _mock_validated_intake_data() -> dict:
    return {
        "first_name": "Jane",
        "last_name": "Doe",
        "birth_year": 1988,
        "phone": "8065551111",
        "email": "jane@example.com",
        "entry_date": "2026-04-12",
        "shelter": "abba",
        "program_status": "active",
        "entry_need_keys": [],
    }


def test_intake_edit_submit_updates_existing_resident_and_redirects(client, monkeypatch):
    import routes.case_management_parts.intake as intake_module

    _disable_admin_only_mode(monkeypatch)
    _set_case_manager_session(client)

    monkeypatch.setattr(intake_module, "init_db", lambda: None)
    monkeypatch.setattr(intake_module, "case_manager_allowed", lambda: True)
    monkeypatch.setattr(
        intake_module,
        "_validate_intake_form",
        lambda form, shelter: (_mock_validated_intake_data(), []),
    )
    monkeypatch.setattr(
        intake_module,
        "resident_enrollment_in_scope",
        lambda resident_id, current_shelter: (
            {"id": resident_id, "first_name": "Jane"},
            {"id": 777, "resident_id": resident_id},
        ),
    )

    captured: dict = {}

    def _fake_update_intake(*, resident_id, enrollment_id, data):
        captured["resident_id"] = resident_id
        captured["enrollment_id"] = enrollment_id
        captured["data"] = data

    monkeypatch.setattr(intake_module, "update_intake", _fake_update_intake)

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/case-management/intake-assessment/new",
        data={
            "_csrf_token": csrf_token,
            "action": "submit",
            "review_passed": "1",
            "resident_id": "55",
            "is_edit_mode": "true",
            "first_name": "Jane",
            "last_name": "Doe",
            "birth_year": "1988",
            "phone": "8065551111",
            "email": "jane@example.com",
            "entry_date": "2026-04-12",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/staff/case-management/55" in response.headers["Location"]
    assert captured["resident_id"] == 55
    assert captured["enrollment_id"] == 777
    assert captured["data"]["first_name"] == "Jane"


def test_intake_edit_submit_handles_missing_enrollment(client, monkeypatch):
    import routes.case_management_parts.intake as intake_module

    _disable_admin_only_mode(monkeypatch)
    _set_case_manager_session(client)

    monkeypatch.setattr(intake_module, "init_db", lambda: None)
    monkeypatch.setattr(intake_module, "case_manager_allowed", lambda: True)
    monkeypatch.setattr(
        intake_module,
        "_validate_intake_form",
        lambda form, shelter: (_mock_validated_intake_data(), []),
    )
    monkeypatch.setattr(
        intake_module,
        "resident_enrollment_in_scope",
        lambda resident_id, current_shelter: (
            {"id": resident_id, "first_name": "Jane"},
            None,
        ),
    )

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/case-management/intake-assessment/new",
        data={
            "_csrf_token": csrf_token,
            "action": "submit",
            "review_passed": "1",
            "resident_id": "55",
            "is_edit_mode": "true",
            "first_name": "Jane",
            "last_name": "Doe",
            "birth_year": "1988",
            "phone": "8065551111",
            "email": "jane@example.com",
            "entry_date": "2026-04-12",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/staff/case-management/55" in response.headers["Location"]


def test_intake_edit_submit_handles_lookup_error_from_update(client, monkeypatch):
    import routes.case_management_parts.intake as intake_module

    _disable_admin_only_mode(monkeypatch)
    _set_case_manager_session(client)

    monkeypatch.setattr(intake_module, "init_db", lambda: None)
    monkeypatch.setattr(intake_module, "case_manager_allowed", lambda: True)
    monkeypatch.setattr(
        intake_module,
        "_validate_intake_form",
        lambda form, shelter: (_mock_validated_intake_data(), []),
    )
    monkeypatch.setattr(
        intake_module,
        "resident_enrollment_in_scope",
        lambda resident_id, current_shelter: (
            {"id": resident_id, "first_name": "Jane"},
            {"id": 777, "resident_id": resident_id},
        ),
    )

    def _raise_lookup_error(*, resident_id, enrollment_id, data):
        raise LookupError("No intake assessment found for update.")

    monkeypatch.setattr(intake_module, "update_intake", _raise_lookup_error)

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/case-management/intake-assessment/new",
        data={
            "_csrf_token": csrf_token,
            "action": "submit",
            "review_passed": "1",
            "resident_id": "55",
            "is_edit_mode": "true",
            "first_name": "Jane",
            "last_name": "Doe",
            "birth_year": "1988",
            "phone": "8065551111",
            "email": "jane@example.com",
            "entry_date": "2026-04-12",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/staff/case-management/55" in response.headers["Location"]


def test_intake_edit_submit_handles_unexpected_update_exception(client, monkeypatch):
    import routes.case_management_parts.intake as intake_module

    _disable_admin_only_mode(monkeypatch)
    _set_case_manager_session(client)

    monkeypatch.setattr(intake_module, "init_db", lambda: None)
    monkeypatch.setattr(intake_module, "case_manager_allowed", lambda: True)
    monkeypatch.setattr(
        intake_module,
        "_validate_intake_form",
        lambda form, shelter: (_mock_validated_intake_data(), []),
    )
    monkeypatch.setattr(
        intake_module,
        "resident_enrollment_in_scope",
        lambda resident_id, current_shelter: (
            {"id": resident_id, "first_name": "Jane"},
            {"id": 777, "resident_id": resident_id},
        ),
    )

    def _raise_runtime_error(*, resident_id, enrollment_id, data):
        raise RuntimeError("boom")

    monkeypatch.setattr(intake_module, "update_intake", _raise_runtime_error)

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/case-management/intake-assessment/new",
        data={
            "_csrf_token": csrf_token,
            "action": "submit",
            "review_passed": "1",
            "resident_id": "55",
            "is_edit_mode": "true",
            "first_name": "Jane",
            "last_name": "Doe",
            "birth_year": "1988",
            "phone": "8065551111",
            "email": "jane@example.com",
            "entry_date": "2026-04-12",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200


def test_intake_review_duplicate_stop_redirects_to_duplicate_review(client, monkeypatch):
    import routes.case_management_parts.intake as intake_module

    _disable_admin_only_mode(monkeypatch)
    _set_case_manager_session(client)

    monkeypatch.setattr(intake_module, "init_db", lambda: None)
    monkeypatch.setattr(intake_module, "case_manager_allowed", lambda: True)
    monkeypatch.setattr(
        intake_module,
        "_validate_intake_form",
        lambda form, shelter: (_mock_validated_intake_data(), []),
    )
    monkeypatch.setattr(
        intake_module,
        "_find_possible_duplicate",
        lambda **kwargs: {"id": 5},
    )
    monkeypatch.setattr(
        intake_module,
        "save_intake_review_decision",
        lambda **kwargs: IntakeReviewResult(
            duplicate_stop=type(
                "Stop",
                (),
                {
                    "draft_id": 999,
                    "duplicate_identifier": "R-000999",
                    "duplicate_first_name": "Jane",
                    "duplicate_last_name": "Doe",
                },
            )()
        ),
    )

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/case-management/intake-assessment/new",
        data={
            "_csrf_token": csrf_token,
            "action": "review",
            "first_name": "Jane",
            "last_name": "Doe",
            "birth_year": "1988",
            "phone": "8065551111",
            "email": "jane@example.com",
            "entry_date": "2026-04-12",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        "/staff/case-management/intake-assessment/duplicate-review/999"
        in response.headers["Location"]
    )
