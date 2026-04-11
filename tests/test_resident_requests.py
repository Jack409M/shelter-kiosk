from __future__ import annotations


def _login_resident(client):
    with client.session_transaction() as session:
        session["resident_id"] = 123
        session["resident_name"] = "Test Resident"


def test_resident_must_be_logged_in(client):
    response = client.get("/resident/requests", follow_redirects=False)

    # should redirect to sign in
    assert response.status_code in (301, 302)


def test_resident_requests_page_loads_when_logged_in(client, monkeypatch):
    import routes.resident_requests as module

    _login_resident(client)

    monkeypatch.setattr(module, "get_resident_requests", lambda resident_id: [])

    response = client.get("/resident/requests", follow_redirects=True)

    assert response.status_code == 200


def test_resident_can_submit_request(client, monkeypatch):
    import routes.resident_requests as module

    _login_resident(client)

    monkeypatch.setattr(module, "create_resident_request", lambda **kwargs: 1)

    response = client.post(
        "/resident/requests",
        data={"request_type": "pass", "notes": "Test"},
        follow_redirects=False,
    )

    # expect redirect after submit
    assert response.status_code in (301, 302)
