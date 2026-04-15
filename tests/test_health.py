from __future__ import annotations

import logging


def test_health_live_returns_ok(client):
    response = client.get("/live")

    assert response.status_code == 200
    assert response.is_json
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["service"] == "shelter-kiosk"


def test_health_ready_returns_ok(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.is_json
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["service"] == "shelter-kiosk"
    assert payload["checks"]["config"]["ok"] is True
    assert payload["checks"]["database"]["ok"] is True


def test_health_ready_returns_500_when_db_returns_no_row(client, monkeypatch, caplog):
    import routes.health as health_module

    monkeypatch.setattr(health_module, "db_fetchone", lambda query: None)

    with caplog.at_level(logging.ERROR):
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.is_json
    payload = response.get_json()
    assert payload["status"] == "error"
    assert payload["checks"]["database"]["ok"] is False
    assert payload["checks"]["database"]["error"] == "RuntimeError"

    messages = [record.getMessage() for record in caplog.records]
    assert any("health_readiness_failed" in message for message in messages)


def test_health_ready_returns_500_and_logs_when_db_raises(client, monkeypatch, caplog):
    import routes.health as health_module

    def _boom(query):
        raise RuntimeError("db is down")

    monkeypatch.setattr(health_module, "db_fetchone", _boom)

    with caplog.at_level(logging.ERROR):
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.is_json
    payload = response.get_json()
    assert payload["status"] == "error"
    assert payload["checks"]["database"]["ok"] is False
    assert payload["checks"]["database"]["error"] == "RuntimeError"

    messages = [record.getMessage() for record in caplog.records]
    assert any("health_readiness_failed" in message for message in messages)


def test_health_ready_does_not_leak_raw_exception_text(client, monkeypatch):
    import routes.health as health_module

    def _boom(query):
        raise RuntimeError("sensitive internal failure details")

    monkeypatch.setattr(health_module, "db_fetchone", _boom)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.is_json
    payload = response.get_json()
    assert payload["status"] == "error"
    assert payload["checks"]["database"]["error"] == "RuntimeError"
    assert b"sensitive internal failure details" not in response.data
