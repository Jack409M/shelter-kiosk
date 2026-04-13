from __future__ import annotations


def test_require_login_redirects_when_no_staff_session(client, monkeypatch):
    import core.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "db_fetchone",
        lambda *args, **kwargs: {"admin_login_only_mode": False},
    )

    response = client.get("/staff/case-management/", follow_redirects=False)

    assert response.status_code == 302
    assert "/staff/login" in response.headers["Location"]


def test_require_shelter_redirects_when_staff_session_has_no_shelter(client, monkeypatch):
    import core.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "db_fetchone",
        lambda *args, **kwargs: {"admin_login_only_mode": False},
    )

    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "case_manager"
        session["role"] = "case_manager"
        session["allowed_shelters"] = ["abba"]

    response = client.get("/staff/case-management/", follow_redirects=False)

    assert response.status_code == 302
    assert "/staff/select-shelter" in response.headers["Location"]


def test_require_shelter_clears_invalid_staff_session_when_shelter_not_allowed(
    client,
    monkeypatch,
):
    import core.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "db_fetchone",
        lambda *args, **kwargs: {"admin_login_only_mode": False},
    )

    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "case_manager"
        session["role"] = "case_manager"
        session["shelter"] = "haven"
        session["allowed_shelters"] = ["abba"]

    response = client.get("/staff/case-management/", follow_redirects=False)

    assert response.status_code == 302
    assert "/staff/login" in response.headers["Location"]

    with client.session_transaction() as session:
        assert "staff_user_id" not in session
        assert "role" not in session


def test_case_management_redirects_non_case_manager_user(client, monkeypatch):
    import core.auth as auth_module
    import routes.case_management_parts.intake as intake_module

    monkeypatch.setattr(
        auth_module,
        "db_fetchone",
        lambda *args, **kwargs: {"admin_login_only_mode": False},
    )
    monkeypatch.setattr(intake_module, "init_db", lambda: None)

    with client.session_transaction() as session:
        session["staff_user_id"] = 2
        session["username"] = "staff_user"
        session["role"] = "staff"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]

    response = client.get(
        "/staff/case-management/intake-assessment/new",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/staff/attendance" in response.headers["Location"]


def test_case_management_allows_case_manager_user(client, monkeypatch):
    import core.auth as auth_module
    import routes.case_management_parts.intake as intake_module

    monkeypatch.setattr(
        auth_module,
        "db_fetchone",
        lambda *args, **kwargs: {"admin_login_only_mode": False},
    )
    monkeypatch.setattr(intake_module, "init_db", lambda: None)
    monkeypatch.setattr(intake_module, "_load_intake_draft", lambda shelter, draft_id: None)

    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "case_manager"
        session["role"] = "case_manager"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]

    response = client.get(
        "/staff/case-management/intake-assessment/new",
        follow_redirects=False,
    )

    assert response.status_code == 200


def test_admin_only_mode_blocks_non_admin_staff_session(client, monkeypatch):
    import core.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "db_fetchone",
        lambda *args, **kwargs: {"admin_login_only_mode": True},
    )

    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "case_manager"
        session["role"] = "case_manager"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]

    response = client.get("/staff/case-management/", follow_redirects=False)

    assert response.status_code == 302
    assert "/staff/login" in response.headers["Location"]

    with client.session_transaction() as session:
        assert "staff_user_id" not in session
        assert "role" not in session


def test_admin_only_mode_allows_admin_staff_session(client, monkeypatch):
    import core.auth as auth_module

    monkeypatch.setattr(
        auth_module,
        "db_fetchone",
        lambda *args, **kwargs: {"admin_login_only_mode": True},
    )

    with client.session_transaction() as session:
        session["staff_user_id"] = 99
        session["username"] = "admin"
        session["role"] = "admin"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]

    response = client.get("/staff/case-management/", follow_redirects=False)

    assert response.status_code == 200
