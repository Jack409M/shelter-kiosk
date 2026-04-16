from __future__ import annotations

import logging


def _set_valid_resident_session(client):
    with client.session_transaction() as sess:
        sess["resident_id"] = "1"
        sess["resident_identifier"] = "ABC123"
        sess["resident_first"] = "Jane"
        sess["resident_last"] = "Doe"
        sess["resident_shelter"] = "GH"


def test_resident_home_requires_signin(client):
    response = client.get("/resident/home")

    assert response.status_code == 302
    assert "/resident" in response.headers["Location"]


def test_resident_home_success_runs_cleanup_and_renders(client, monkeypatch):
    import routes.resident_portal as portal

    _set_valid_resident_session(client)

    called = {"cleanup": False}

    monkeypatch.setattr(portal, "get_db", lambda: object())

    def _cleanup(shelter):
        called["cleanup"] = True

    monkeypatch.setattr(portal, "run_pass_retention_cleanup_for_shelter", _cleanup)
    monkeypatch.setattr(portal, "_load_recent_pass_items", lambda rid, s: [{"ok": True}])
    monkeypatch.setattr(portal, "render_template", lambda name, **ctx: "ok")

    response = client.get("/resident/home")

    assert response.status_code == 200
    assert response.data == b"ok"
    assert called["cleanup"] is True


def test_resident_home_logs_and_clears_session_on_failure(client, monkeypatch, caplog):
    import routes.resident_portal as portal

    _set_valid_resident_session(client)

    def _boom():
        raise RuntimeError("db fail")

    monkeypatch.setattr(portal, "get_db", _boom)

    with caplog.at_level(logging.ERROR):
        response = client.get("/resident/home")

    assert response.status_code == 302
    assert "/resident" in response.headers["Location"]

    with client.session_transaction() as sess:
        assert "resident_id" not in sess

    messages = [r.getMessage() for r in caplog.records]
    assert any("resident_portal_home_failed" in m for m in messages)


def test_resident_chores_logs_and_clears_session_on_failure(client, monkeypatch, caplog):
    import routes.resident_portal as portal

    _set_valid_resident_session(client)

    monkeypatch.setattr(portal, "get_db", lambda: object())

    def _boom(*args, **kwargs):
        raise RuntimeError("render fail")

    monkeypatch.setattr(portal, "render_template", _boom)

    with caplog.at_level(logging.ERROR):
        response = client.get("/resident/chores")

    assert response.status_code == 302

    with client.session_transaction() as sess:
        assert "resident_id" not in sess

    messages = [r.getMessage() for r in caplog.records]
    assert any("resident_portal_chores_failed" in m for m in messages)
