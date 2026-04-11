from __future__ import annotations


def test_create_app_builds_successfully():
    from core.app_factory import create_app

    app = create_app()

    assert app is not None
    assert app.config["TESTING"] is False


def test_expected_blueprints_are_registered(app):
    expected = {
        "auth",
        "admin",
        "attendance",
        "case_management",
        "public",
        "resident_requests",
    }

    registered = set(app.blueprints.keys())

    missing = expected - registered
    assert not missing, f"Missing blueprints: {sorted(missing)}"
