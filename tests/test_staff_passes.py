from __future__ import annotations


def _set_csrf_token(client, token: str = "test-csrf-token") -> str:
    with client.session_transaction() as session:
        session["_csrf_token"] = token
    return token


def _login_staff(client, role="case_manager"):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = role
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]


def test_pass_review_requires_login(client):
    response = client.get("/staff/leave/pending", follow_redirects=False)

    assert response.status_code in (301, 302)
    assert "/staff/login" in response.headers["Location"]


def test_pass_review_page_loads_for_staff(client):
    _login_staff(client)

    response = client.get("/staff/leave/pending", follow_redirects=False)

    assert response.status_code in (301, 302)
    assert "/staff/passes/pending" in response.headers["Location"]


def test_pass_approval_flow(client):
    _login_staff(client)
    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/leave/1/approve",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/passes/pending" in response.headers["Location"]


def test_pass_denial_flow(client):
    _login_staff(client)
    csrf_token = _set_csrf_token(client)

    response = client.post(
        "/staff/leave/1/deny",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/passes/pending" in response.headers["Location"]
