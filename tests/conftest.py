from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/testdb")
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setenv("CLOUDFLARE_ONLY", "0")
    monkeypatch.setenv("ENABLE_DEBUG_ROUTES", "0")
    monkeypatch.setenv("ENABLE_DANGEROUS_ADMIN_ROUTES", "0")
    monkeypatch.setenv("TWILIO_ENABLED", "0")
    monkeypatch.setenv("TWILIO_INBOUND_ENABLED", "0")
    monkeypatch.setenv("TWILIO_STATUS_ENABLED", "0")


@pytest.fixture
def app():
    from core.app_factory import create_app

    app = create_app()
    app.config.update(
        TESTING=True,
        DEBUG=True,
    )
    return app


@pytest.fixture
def client(app):
    return app.test_client()
