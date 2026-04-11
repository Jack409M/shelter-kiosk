from __future__ import annotations


def _login_staff(client):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = "case_manager"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]


def test_future_pass_review_endpoint_exists(client):
    _login_staff(client)

    response = client.get("/staff/passes/pending", follow_redirects=False)

    # this is expected to FAIL right now
    assert response.status_code != 404
