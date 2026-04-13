from __future__ import annotations

from core.intake_service import (
    IntakeCreateResult,
    IntakeDuplicateStop,
    IntakeReviewResult,
)


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


def test_intake_final_submit_requires_review_passed(client, monkeypatch):
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

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/case-management/intake-assessment/new",
        data={
            "_csrf_token": csrf_token,
            "action": "submit",
            "first_name": "Jane",
            "last_name": "Doe",
            "entry_date": "2026-04-12",
            "shelter": "abba",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"Submit the basic identity information for review before finalizing intake."
        in response.data
    )


def test_intake_review_no_duplicate_redirects_back_to_form_with_draft_id(
    client,
    monkeypatch,
):
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
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        intake_module,
        "save_intake_review_decision",
        lambda **kwargs: IntakeReviewResult(
            approved_draft_id=123,
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
        "/staff/case-management/intake-assessment/new?draft_id=123"
        in response.headers["Location"]
    )


def test_intake_review_duplicate_redirects_to_duplicate_review(client, monkeypatch):
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
        lambda **kwargs: {"id": 77},
    )
    monkeypatch.setattr(
        intake_module,
        "save_intake_review_decision",
        lambda **kwargs: IntakeReviewResult(
            duplicate_stop=IntakeDuplicateStop(
                draft_id=456,
                duplicate_identifier="R-000456",
                duplicate_first_name="Jane",
                duplicate_last_name="Doe",
            )
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
        "/staff/case-management/intake-assessment/duplicate-review/456"
        in response.headers["Location"]
    )


def test_intake_final_submit_creates_resident_and_redirects_to_edit(client, monkeypatch):
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
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        intake_module,
        "create_intake",
        lambda **kwargs: IntakeCreateResult(
            resident_id=99,
            resident_identifier="R-000099",
            resident_code="RC99",
        ),
    )

    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/case-management/intake-assessment/new",
        data={
            "_csrf_token": csrf_token,
            "action": "submit",
            "review_passed": "1",
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
    assert "/staff/case-management/99/intake-edit" in response.headers["Location"]
