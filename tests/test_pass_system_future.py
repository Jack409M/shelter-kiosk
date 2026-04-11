from __future__ import annotations


def _login_staff(client):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = "case_manager"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]


def test_pass_review_endpoint_returns_200(client, monkeypatch):
    import core.pass_retention as retention_module
    import routes.attendance_parts.passes as passes_module

    _login_staff(client)

    monkeypatch.setattr(retention_module, "run_pass_retention_cleanup_for_shelter", lambda shelter: None)
    monkeypatch.setattr(passes_module, "db_fetchall", lambda *args, **kwargs: [])
    monkeypatch.setattr(passes_module, "db_execute", lambda *args, **kwargs: None)

    response = client.get("/staff/passes/pending", follow_redirects=True)

    assert response.status_code == 200


def test_pass_review_page_contains_expected_text(client, monkeypatch):
    import core.pass_retention as retention_module
    import routes.attendance_parts.passes as passes_module

    _login_staff(client)

    monkeypatch.setattr(retention_module, "run_pass_retention_cleanup_for_shelter", lambda shelter: None)
    monkeypatch.setattr(passes_module, "db_fetchall", lambda *args, **kwargs: [])
    monkeypatch.setattr(passes_module, "db_execute", lambda *args, **kwargs: None)

    response = client.get("/staff/passes/pending", follow_redirects=True)

    assert response.status_code == 200
    assert b"pass" in response.data.lower() or b"request" in response.data.lower()
