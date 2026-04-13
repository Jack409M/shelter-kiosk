from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    test_db_path = tmp_path / "test_app.sqlite3"
    test_database_url = f"sqlite:///{test_db_path}"

    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setenv("CLOUDFLARE_ONLY", "0")
    monkeypatch.setenv("ENABLE_DEBUG_ROUTES", "0")
    monkeypatch.setenv("ENABLE_DANGEROUS_ADMIN_ROUTES", "0")
    monkeypatch.setenv("TWILIO_ENABLED", "0")
    monkeypatch.setenv("TWILIO_INBOUND_ENABLED", "0")
    monkeypatch.setenv("TWILIO_STATUS_ENABLED", "0")

    import core.db as core_db
    import core.runtime as core_runtime
    import db.schema as schema_module

    core_db.PG_POOL = None
    core_runtime._DB_INITIALIZED = False
    core_runtime._DB_INIT_URL = None
    schema_module._SCHEMA_INITIALIZED = False


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "core.app_factory.start_pass_retention_scheduler",
        lambda app: None,
    )

    from core.app_factory import create_app
    from core.runtime import init_db

    app = create_app()
    app.config.update(
        TESTING=True,
        DEBUG=True,
    )

    with app.app_context():
        init_db()

    return app


@pytest.fixture
def client(app):
    return app.test_client()
