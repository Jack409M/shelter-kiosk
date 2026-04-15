from __future__ import annotations

import logging

from core.app_factory import create_app


def test_log_level_debug_is_honored(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setattr("core.app_factory.start_pass_retention_scheduler", lambda app: None)

    app = create_app({"TESTING": True, "DATABASE_URL": f"sqlite:///{db_path}"})

    assert app.logger.level == logging.DEBUG


def test_invalid_log_level_falls_back_to_info(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_REAL_LEVEL")
    monkeypatch.setattr("core.app_factory.start_pass_retention_scheduler", lambda app: None)

    app = create_app({"TESTING": True, "DATABASE_URL": f"sqlite:///{db_path}"})

    assert app.logger.level == logging.INFO
