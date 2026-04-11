from __future__ import annotations


def _login_staff(client, role="case_manager"):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = role
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]


def test_pass_review_requires_login(client):
    response = client.get("/staff/passes", follow_redirects=False)

    assert response.status_code in (301, 302)
    assert "/staff/login" in response.headers["Location"]


def test_pass_review_page_loads_for_staff(client, monkeypatch):
    import routes.staff_portal as module

    _login_staff(client)

    monkeypatch.setattr(module, "get_pending_passes", lambda shelter: [])

    response = client.get("/staff/passes", follow_redirects=True)

    assert response.status_code == 200


def test_pass_approval_flow(client, monkeypatch):
    import routes.staff_portal as module

    _login_staff(client)

    monkeypatch.setattr(module, "approve_pass_request", lambda pass_id, staff_id: True)
    monkeypatch.setattr(module, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        "/staff/passes/approve",
        data={"pass_id": 1},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)


def test_pass_denial_flow(client, monkeypatch):
    import routes.staff_portal as module

    _login_staff(client)

    monkeypatch.setattr(module, "deny_pass_request", lambda pass_id, staff_id, reason=None: True)
    monkeypatch.setattr(module, "log_action", lambda *args, **kwargs: None)

    response = client.post(
        "/staff/passes/deny",
        data={"pass_id": 1, "reason": "Invalid"},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
