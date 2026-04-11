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


def test_staff_pass_detail_page_renders(client, monkeypatch):
    import routes.attendance_parts.passes as passes_module

    _login_staff(client)

    monkeypatch.setattr(
        passes_module,
        "load_staff_pass_detail_context",
        lambda **kwargs: {
            "p": {"id": 1, "resident_name": "Test Resident"},
            "pass_detail": {},
            "hour_summary": {},
            "meeting_summary": {},
            "resident_level": 1,
            "sponsor_name": "",
            "sponsor_active": False,
            "step_current": None,
            "step_work_active": False,
            "monthly_income": None,
            "policy_check": {},
        },
    )

    response = client.get("/staff/passes/1", follow_redirects=True)

    assert response.status_code == 200


def test_staff_pass_approve_redirects(client, monkeypatch):
    import routes.attendance_parts.passes as passes_module

    _login_staff(client)
    csrf_token = _set_csrf_token(client)

    monkeypatch.setattr(
        passes_module,
        "approve_pass_request",
        lambda **kwargs: (True, "attendance.staff_passes_pending", "Approved.", "ok"),
    )

    response = client.post(
        "/staff/passes/1/approve",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/passes/pending" in response.headers["Location"]


def test_staff_pass_deny_redirects(client, monkeypatch):
    import routes.attendance_parts.passes as passes_module

    _login_staff(client)
    csrf_token = _set_csrf_token(client)

    monkeypatch.setattr(
        passes_module,
        "deny_pass_request",
        lambda **kwargs: (True, "attendance.staff_passes_pending", "Denied.", "ok"),
    )

    response = client.post(
        "/staff/passes/1/deny",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/passes/pending" in response.headers["Location"]


def test_staff_pass_check_in_redirects(client, monkeypatch):
    import routes.attendance_parts.passes as passes_module

    _login_staff(client)
    csrf_token = _set_csrf_token(client)

    monkeypatch.setattr(
        passes_module,
        "check_in_pass_return",
        lambda **kwargs: (True, "attendance.staff_passes_away_now", "Checked in.", "ok"),
    )

    response = client.post(
        "/staff/passes/1/check-in",
        data={"_csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)
    assert "/staff/passes/away-now" in response.headers["Location"]
