from __future__ import annotations

import logging


def test_health_live_returns_ok(client):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {"status": "ok"}


def test_health_ready_returns_ok(client):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {"status": "ok"}


def test_health_ready_returns_500_when_db_returns_no_row(client, monkeypatch, caplog):
    import routes.health as health_module

    monkeypatch.setattr(health_module, "init_db", lambda: None)
    monkeypatch.setattr(health_module, "db_fetchone", lambda query: None)

    with caplog.at_level(logging.ERROR):
        response = client.get("/health/ready")

    assert response.status_code == 500
    assert response.is_json
    assert response.get_json() == {"status": "error", "reason": "db_no_response"}

    messages = [record.getMessage() for record in caplog.records]
    assert any("health_ready_failed reason=db_no_response" in message for message in messages)


def test_health_ready_returns_500_and_logs_when_db_raises(client, monkeypatch, caplog):
    import routes.health as health_module

    monkeypatch.setattr(health_module, "init_db", lambda: None)

    def _boom(query):
        raise RuntimeError("db is down")

    monkeypatch.setattr(health_module, "db_fetchone", _boom)

    with caplog.at_level(logging.ERROR):
        response = client.get("/health/ready")

    assert response.status_code == 500
    assert response.is_json
    assert response.get_json() == {"status": "error", "reason": "db_exception"}

    messages = [record.getMessage() for record in caplog.records]
    assert any("health_ready_failed reason=db_exception" in message for message in messages)


def test_health_ready_does_not_leak_raw_exception_text(client, monkeypatch):
    import routes.health as health_module

    monkeypatch.setattr(health_module, "init_db", lambda: None)

    def _boom(query):
        raise RuntimeError("sensitive internal failure details")

    monkeypatch.setattr(health_module, "db_fetchone", _boom)

    response = client.get("/health/ready")

    assert response.status_code == 500
    assert response.is_json
    assert response.get_json() == {"status": "error", "reason": "db_exception"}
    assert b"sensitive internal failure details" not in response.data
