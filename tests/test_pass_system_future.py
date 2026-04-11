from __future__ import annotations


def _login_staff(client):
    with client.session_transaction() as session:
        session["staff_user_id"] = 1
        session["username"] = "staff"
        session["role"] = "case_manager"
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]


def test_pass_review_endpoint_returns_200(client, monkeypatch):
    import routes.attendance_parts.passes as passes_module

    _login_staff(client)

    monkeypatch.setattr(passes_module, "run_pass_retention_cleanup_for_shelter", lambda shelter: None)
    monkeypatch.setattr(passes_module, "fetch_pending_pass_rows", lambda shelter: [])
    monkeypatch.setattr(passes_module, "has_active_pass_block", lambda resident_id: (False, []))

    response = client.get("/staff/passes/pending", follow_redirects=True)

    assert response.status_code == 200


def test_pass_review_page_contains_expected_text(client, monkeypatch):
    import routes.attendance_parts.passes as passes_module

    _login_staff(client)

    monkeypatch.setattr(passes_module, "run_pass_retention_cleanup_for_shelter", lambda shelter: None)
    monkeypatch.setattr(
        passes_module,
        "fetch_pending_pass_rows",
        lambda shelter: [
            {
                "resident_id": 123,
                "resident_name": "Test Resident",
                "pass_type": "pass",
                "status": "pending",
            }
        ],
    )
    monkeypatch.setattr(passes_module, "has_active_pass_block", lambda resident_id: (False, []))

    response = client.get("/staff/passes/pending", follow_redirects=True)

    assert response.status_code == 200
    assert b"pass" in response.data.lower() or b"request" in response.data.lower()
