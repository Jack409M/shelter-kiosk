from __future__ import annotations

import logging

import pytest


def _build_app(monkeypatch, tmp_path, log_level: str = "INFO"):
    db_path = tmp_path / "test_logging.db"
    database_url = f"sqlite:///{db_path}"

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setenv("CLOUDFLARE_ONLY", "0")
    monkeypatch.setenv("ENABLE_DEBUG_ROUTES", "0")
    monkeypatch.setenv("ENABLE_DANGEROUS_ADMIN_ROUTES", "0")
    monkeypatch.setenv("TWILIO_ENABLED", "0")
    monkeypatch.setenv("TWILIO_INBOUND_ENABLED", "0")
    monkeypatch.setenv("TWILIO_STATUS_ENABLED", "0")
    monkeypatch.setenv("LOG_LEVEL", log_level)

    monkeypatch.setattr(
        "core.app_factory.start_pass_retention_scheduler",
        lambda app: None,
    )

    import core.db as db_module
    import core.runtime as runtime
    from db import schema

    runtime._DB_INITIALIZED = False
    runtime._DB_INIT_URL = None
    db_module.PG_POOL = None
    schema._SCHEMA_INITIALIZED_KEY = None

    from core.app_factory import create_app

    app = create_app(
        {
            "TESTING": True,
            "DEBUG": True,
            "DATABASE_URL": database_url,
        }
    )

    return app


def test_log_level_debug_is_honored(monkeypatch, tmp_path):
    app = _build_app(monkeypatch, tmp_path, log_level="DEBUG")

    assert app.logger.level == logging.DEBUG


def test_invalid_log_level_falls_back_to_info(monkeypatch, tmp_path):
    app = _build_app(monkeypatch, tmp_path, log_level="NOT_A_REAL_LEVEL")

    assert app.logger.level == logging.INFO


def test_startup_logs_are_emitted(monkeypatch, tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        _build_app(monkeypatch, tmp_path, log_level="INFO")

    messages = [record.getMessage() for record in caplog.records]

    assert any("Shelter Kiosk starting" in message for message in messages)
    assert any("database_mode=" in message for message in messages)
    assert any("blueprints_loaded=" in message for message in messages)


def test_unhandled_exception_is_logged(app, client, caplog):
    @app.route("/_test/logging_boom")
    def logging_boom():
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        response = client.get("/_test/logging_boom")

    assert response.status_code == 500

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "Unhandled exception" in message or "Internal server error" in message
        for message in messages
    )


def test_health_ready_failure_is_logged(client, monkeypatch, caplog):
    import routes.health as health_module

    monkeypatch.setattr(health_module, "init_db", lambda: None)

    def _boom(query):
        raise RuntimeError("boom")

    monkeypatch.setattr(health_module, "db_fetchone", _boom)

    with caplog.at_level(logging.ERROR):
        response = client.get("/health/ready")

    assert response.status_code == 500
    assert any("health_ready_failed" in record.getMessage() for record in caplog.records)
