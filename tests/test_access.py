from __future__ import annotations

import pytest
from flask import Flask, session


@pytest.fixture
def app():
    app = Flask(__name__)
    app.secret_key = "test"
    return app


@pytest.fixture
def ctx(app):
    with app.test_request_context("/test"):
        yield


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def test_clean_session_text_handles_none_and_whitespace(ctx):
    import core.access as module

    session["x"] = None
    assert module._clean_session_text("x") == ""

    session["x"] = "  hello "
    assert module._clean_session_text("x") == "hello"


def test_session_int_valid_and_invalid(ctx):
    import core.access as module

    session["x"] = "5"
    assert module._session_int("x") == 5

    session["x"] = ""
    assert module._session_int("x") is None

    session["x"] = "bad"
    assert module._session_int("x") is None


# ------------------------------------------------------------
# Staff access
# ------------------------------------------------------------

def test_require_staff_or_admin_allows_valid_role(ctx, monkeypatch):
    import core.access as module

    monkeypatch.setattr(module, "STAFF_ROLES", {"admin", "staff"})

    session["role"] = "admin"

    called = []

    @module.require_staff_or_admin
    def fn():
        called.append(True)
        return "ok"

    result = fn()

    assert result == "ok"
    assert called == [True]


def test_require_staff_or_admin_blocks_invalid_role(ctx, monkeypatch):
    import core.access as module

    monkeypatch.setattr(module, "STAFF_ROLES", {"admin", "staff"})

    session["role"] = "resident"

    @module.require_staff_or_admin
    def fn():
        return "ok"

    result = fn()

    assert result.status_code == 302
    assert "/attendance" in result.location


def test_require_admin_blocks_non_admin(ctx):
    import core.access as module

    session["role"] = "staff"

    @module.require_admin
    def fn():
        return "ok"

    result = fn()

    assert result.status_code == 302
    assert "/attendance" in result.location


def test_require_admin_allows_admin(ctx):
    import core.access as module

    session["role"] = "admin"

    @module.require_admin
    def fn():
        return "ok"

    assert fn() == "ok"


# ------------------------------------------------------------
# Resident access
# ------------------------------------------------------------

def test_require_resident_allows_valid_session(ctx):
    import core.access as module

    session.update({
        "resident_id": "5",
        "resident_identifier": "abc",
        "resident_first": "John",
        "resident_last": "Doe",
        "resident_shelter": "abba",
    })

    @module.require_resident
    def fn():
        return "ok"

    assert fn() == "ok"


def test_require_resident_blocks_missing_fields(ctx):
    import core.access as module

    session.clear()

    @module.require_resident
    def fn():
        return "ok"

    result = fn()

    assert result.status_code == 302
    assert "resident_signin" in result.location


def test_require_resident_blocks_partial_session(ctx):
    import core.access as module

    session.update({
        "resident_id": "5",
        "resident_identifier": "",
        "resident_first": "John",
        "resident_last": "Doe",
        "resident_shelter": "abba",
    })

    @module.require_resident
    def fn():
        return "ok"

    result = fn()

    assert result.status_code == 302


# ------------------------------------------------------------
# Transfer access
# ------------------------------------------------------------

def test_require_transfer_allows_valid(ctx, monkeypatch):
    import core.access as module

    monkeypatch.setattr(module, "TRANSFER_ROLES", {"admin", "case_manager"})

    session["role"] = "admin"

    @module.require_transfer
    def fn():
        return "ok"

    assert fn() == "ok"


def test_require_transfer_blocks_invalid(ctx, monkeypatch):
    import core.access as module

    monkeypatch.setattr(module, "TRANSFER_ROLES", {"admin", "case_manager"})

    session["role"] = "resident"

    @module.require_transfer
    def fn():
        return "ok"

    result = fn()

    assert result.status_code == 302


# ------------------------------------------------------------
# Resident create access
# ------------------------------------------------------------

def test_require_resident_create_allows_valid(ctx):
    import core.access as module

    session["role"] = "admin"

    @module.require_resident_create
    def fn():
        return "ok"

    assert fn() == "ok"


def test_require_resident_create_blocks_invalid(ctx):
    import core.access as module

    session["role"] = "resident"

    @module.require_resident_create
    def fn():
        return "ok"

    result = fn()

    assert result.status_code == 302
