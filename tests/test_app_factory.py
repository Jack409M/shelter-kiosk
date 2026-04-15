from __future__ import annotations

import os

from core.app_factory import _resolve_session_cookie_name, _resolve_session_cookie_secure


def test_create_app_sets_expected_core_config(app):
    assert app.config["MAX_CONTENT_LENGTH"] == 2 * 1024 * 1024
    assert app.config["DATABASE_URL"] == os.environ["DATABASE_URL"]
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["SESSION_COOKIE_NAME"] == "shelter_session"
    assert app.config["SESSION_REFRESH_EACH_REQUEST"] is False


def test_create_app_registers_expected_template_helpers(app):
    assert "csrf_token" in app.jinja_env.globals
    assert "safe_url_for" in app.jinja_env.globals
    assert "shelter_display" in app.jinja_env.globals

    assert "app_date" in app.jinja_env.filters
    assert "app_dt" in app.jinja_env.filters
    assert "app_time" in app.jinja_env.filters
    assert "chi_date" in app.jinja_env.filters
    assert "chi_dt" in app.jinja_env.filters
    assert "chi_time" in app.jinja_env.filters


def test_create_app_registers_expected_blueprints(app):
    expected = {
        "admin",
        "attendance",
        "auth",
        "case_management",
        "public",
        "resident_requests",
        "resident_portal",
        "transport",
        "twilio",
    }

    registered = set(app.blueprints.keys())
    missing = expected - registered

    assert not missing, f"Missing blueprints: {sorted(missing)}"


def test_resolve_session_cookie_secure_uses_explicit_truthy_env(monkeypatch):
    from flask import Flask

    monkeypatch.setenv("COOKIE_SECURE", "1")

    app = Flask(__name__)
    app.config.update(TESTING=False, DEBUG=False)

    assert _resolve_session_cookie_secure(app) is True


def test_resolve_session_cookie_secure_uses_explicit_falsey_env(monkeypatch):
    from flask import Flask

    monkeypatch.setenv("COOKIE_SECURE", "0")

    app = Flask(__name__)
    app.config.update(TESTING=False, DEBUG=False)

    assert _resolve_session_cookie_secure(app) is False


def test_resolve_session_cookie_secure_defaults_false_in_testing(monkeypatch):
    from flask import Flask

    monkeypatch.delenv("COOKIE_SECURE", raising=False)

    app = Flask(__name__)
    app.config.update(TESTING=True, DEBUG=False)

    assert _resolve_session_cookie_secure(app) is False


def test_resolve_session_cookie_secure_defaults_false_in_debug(monkeypatch):
    from flask import Flask

    monkeypatch.delenv("COOKIE_SECURE", raising=False)

    app = Flask(__name__)
    app.config.update(TESTING=False, DEBUG=True)

    assert _resolve_session_cookie_secure(app) is False


def test_resolve_session_cookie_secure_defaults_true_in_production_like_app(monkeypatch):
    from flask import Flask

    monkeypatch.delenv("COOKIE_SECURE", raising=False)

    app = Flask(__name__)
    app.config.update(TESTING=False, DEBUG=False)

    assert _resolve_session_cookie_secure(app) is True


def test_resolve_session_cookie_name_uses_host_prefix_when_secure():
    assert _resolve_session_cookie_name(True) == "__Host-shelter_session"


def test_resolve_session_cookie_name_uses_standard_name_when_not_secure():
    assert _resolve_session_cookie_name(False) == "shelter_session"
