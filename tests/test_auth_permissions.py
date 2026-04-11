from __future__ import annotations


def _login_as(client, role="admin"):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "admin"
        session["role"] = role
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]


def test_require_login_redirects_when_not_logged_in(client):
    response = client.get("/staff/admin/dashboard", follow_redirects=False)

    assert response.status_code in (301, 302)
    assert "/staff/login" in response.headers["Location"]


def test_require_login_allows_logged_in_user(client):
    _login_as(client)

    response = client.get("/staff/admin/dashboard", follow_redirects=False)

    # should not redirect to login
    assert response.status_code != 302 or "/staff/login" not in response.headers.get("Location", "")


def test_non_admin_cannot_access_admin_route(client):
    _login_as(client, role="staff")

    response = client.get("/staff/admin/dashboard", follow_redirects=False)

    # either redirected or blocked
    assert response.status_code in (302, 403)
