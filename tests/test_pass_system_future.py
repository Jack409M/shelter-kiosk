from __future__ import annotations


def _login_staff(client):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = "case_manager"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]


def test_pass_review_endpoint_returns_200(client):
    _login_staff(client)

    response = client.get("/staff/passes/pending", follow_redirects=True)

    assert response.status_code == 200


def test_pass_review_page_contains_expected_text(client):
    _login_staff(client)

    response = client.get("/staff/passes/pending", follow_redirects=True)

    assert response.status_code == 200

    # very light contract checks
    # we are not guessing full UI yet, just making sure page is real
    assert b"pass" in response.data.lower() or b"request" in response.data.lower()
