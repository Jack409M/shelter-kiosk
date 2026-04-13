from __future__ import annotations

import os
import sys
import tempfile

import pytest

# ------------------------------------------------------------
# Ensure project root is on path
# ------------------------------------------------------------

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ------------------------------------------------------------
# FORCE SAFE DEFAULT ENV BEFORE ANY IMPORTS
# ------------------------------------------------------------

_DEFAULT_DB_PATH = os.path.join(tempfile.gettempdir(), "shelter_kiosk_test_bootstrap.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_DEFAULT_DB_PATH}"
os.environ["FLASK_SECRET_KEY"] = "test-secret"
os.environ["COOKIE_SECURE"] = "0"
os.environ["CLOUDFLARE_ONLY"] = "0"
os.environ["ENABLE_DEBUG_ROUTES"] = "0"
os.environ["ENABLE_DANGEROUS_ADMIN_ROUTES"] = "0"
os.environ["TWILIO_ENABLED"] = "0"
os.environ["TWILIO_INBOUND_ENABLED"] = "0"
os.environ["TWILIO_STATUS_ENABLED"] = "0"

# ------------------------------------------------------------
# TEST FIXTURES
# ------------------------------------------------------------


@pytest.fixture
def app(tmp_path, monkeypatch):
    """
    Creates a clean app with isolated SQLite DB per test.
    """

    db_path = tmp_path / "test.db"
    database_url = f"sqlite:///{db_path}"

    monkeypatch.setenv("DATABASE_URL", database_url)

    monkeypatch.setattr(
        "core.app_factory.start_pass_retention_scheduler",
        lambda app: None,
    )

    import core.db as db_module
    import core.runtime as runtime

    runtime._DB_INITIALIZED = False
    runtime._DB_INIT_URL = None
    db_module.PG_POOL = None

    from core.app_factory import create_app

    app = create_app(
        {
            "TESTING": True,
            "DEBUG": True,
            "DATABASE_URL": database_url,
        }
    )

    yield app

    runtime._DB_INITIALIZED = False
    runtime._DB_INIT_URL = None
    db_module.PG_POOL = None


@pytest.fixture
def client(app):
    return app.test_client()
