from __future__ import annotations


def test_csrf_blocks_post_without_token(client, monkeypatch):
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
        session["shelter"] = "abba"
        session["allowed_shelters"] = ["abba"]

    response = client.post(
        "/staff/case-management/intake-assessment/new",
        data={
            "action": "review",
            "first_name": "Jane",
            "last_name": "Doe",
            "entry_date": "2026-04-12",
            "shelter": "abba",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302


def test_resident_context_500_clears_session_and_redirects(client, monkeypatch):
    import routes.resident_portal as portal

    with client.session_transaction() as session:
        session["resident_id"] = 1
        session["resident_identifier"] = "R-000001"
        session["resident_first"] = "Jane"
        session["resident_last"] = "Doe"
        session["resident_shelter"] = "abba"
        session["sms_consent_done"] = True

    monkeypatch.setattr(
        portal,
        "run_pass_retention_cleanup_for_shelter",
        lambda shelter: None,
    )
    monkeypatch.setattr(
        portal,
        "_load_recent_pass_items",
        lambda resident_id, shelter: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = client.get("/resident/home", follow_redirects=False)

    assert response.status_code == 302
    assert "/" in response.headers["Location"]

    with client.session_transaction() as session:
        assert "resident_id" not in session


def test_public_post_rate_limit_returns_429(client, monkeypatch):
    import core.request_security as rs

    app = client.application

    captured_before = list(app.before_request_funcs.get(None, []))
    target = None
    for fn in captured_before:
        if getattr(fn, "__name__", "") == "public_bot_throttle":
            target = fn
            break

    assert target is not None

    monkeypatch.setattr(rs, "log_action", lambda *args, **kwargs: None)

    app.before_request_funcs[None] = [fn for fn in captured_before if fn is not target]

    try:
        with app.test_request_context("/resident", method="POST"):
            result = target()
            assert result is not None
            body, status = result
            assert status == 429
    finally:
        app.before_request_funcs[None] = captured_before


def test_bad_method_is_blocked(client):
    response = client.open("/resident", method="TRACE", follow_redirects=False)

    assert response.status_code == 405
