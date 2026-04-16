from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ------------------------------------------------------------
# Ensure project root is on path
# ------------------------------------------------------------

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ------------------------------------------------------------
# Safe baseline env for import time behavior
# ------------------------------------------------------------

_DEFAULT_DB_PATH = Path(os.getenv("TMPDIR", "/tmp")) / "shelter_kiosk_test_bootstrap.db"

os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("COOKIE_SECURE", "0")
os.environ.setdefault("CLOUDFLARE_ONLY", "0")
os.environ.setdefault("ENABLE_DEBUG_ROUTES", "0")
os.environ.setdefault("ENABLE_DANGEROUS_ADMIN_ROUTES", "0")
os.environ.setdefault("TWILIO_ENABLED", "0")
os.environ.setdefault("TWILIO_INBOUND_ENABLED", "0")
os.environ.setdefault("TWILIO_STATUS_ENABLED", "0")


def _apply_test_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setenv("CLOUDFLARE_ONLY", "0")
    monkeypatch.setenv("ENABLE_DEBUG_ROUTES", "0")
    monkeypatch.setenv("ENABLE_DANGEROUS_ADMIN_ROUTES", "0")
    monkeypatch.setenv("TWILIO_ENABLED", "0")
    monkeypatch.setenv("TWILIO_INBOUND_ENABLED", "0")
    monkeypatch.setenv("TWILIO_STATUS_ENABLED", "0")


def _reset_shared_db_process_state() -> None:
    import core.db as db_module

    db_module.PG_POOL = None


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    database_url = f"sqlite:///{db_path}"

    _apply_test_env(monkeypatch, database_url)
    _reset_shared_db_process_state()

    from core.app_factory import create_app

    app = create_app(
        {
            "TESTING": True,
            "DEBUG": True,
            "DATABASE_URL": database_url,
            "INITIALIZE_DATABASE_ON_STARTUP": True,
            "START_PASS_RETENTION_SCHEDULER": False,
        }
    )

    yield app

    _reset_shared_db_process_state()


@pytest.fixture
def client(app):
    return app.test_client()
