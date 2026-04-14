from __future__ import annotations

import os


def test_create_app_sets_expected_core_config(app):
    assert app.config["MAX_CONTENT_LENGTH"] == 2 * 1024 * 1024
    assert app.config["DATABASE_URL"] == os.environ["DATABASE_URL"]
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


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
