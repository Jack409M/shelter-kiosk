from __future__ import annotations

from datetime import datetime

import pytest


def _login_staff(client, *, shelter: str = "abba", staff_user_id: int = 7) -> None:
    with client.session_transaction() as session:
        session["role"] = "staff"
        session["username"] = "staffuser"
        session["staff_user_id"] = staff_user_id
        session["shelter"] = shelter
        session.modified = True  # 🔥 critical for POST persistence


def _force_session(client):
    # ensures Flask commits session before request
    with client.session_transaction() as session:
        session.modified = True


def test_to_chicago_handles_blank_and_invalid():
    import routes.transport as module

    assert module._to_chicago(None) is None
    assert module._to_chicago("") is None
    assert module._to_chicago("not-a-date") is None


def test_to_chicago_and_local_day_handle_naive_and_aware_datetimes():
    import routes.transport as module

    naive_local = module._to_chicago("2026-04-15T12:00:00")
    aware_local = module._to_chicago("2026-04-15T12:00:00+00:00")

    assert naive_local is not None
    assert aware_local is not None
    assert naive_local.tzinfo is not None
    assert aware_local.tzinfo is not None

    assert module._local_day("2026-04-15T12:00:00+00:00") == "2026-04-15"
    assert module._local_day(None) is None
    assert module._local_day("bad-date") is None


def test_row_value_prefers_dict_and_falls_back_by_index():
    import routes.transport as module

    assert module._row_value({"needed_at": "x"}, "needed_at", 5, "") == "x"
    assert module._row_value(("a", "b", "c"), "ignored", 1, "") == "b"
    assert module._row_value(("a",), "ignored", 5, "fallback") == "fallback"


def test_pending_requires_permission(client, monkeypatch):
    import routes.transport as module

    _login_staff(client)
    _force_session(client)

    monkeypatch.setattr(module, "_can_manage_transport", lambda: False)

    response = client.get("/staff/transport/pending", follow_redirects=False)

    assert response.status_code == 302
    assert "/staff/attendance" in response.headers["Location"]


def test_schedule_requires_permission(client, monkeypatch):
    import routes.transport as module

    _login_staff(client)
    _force_session(client)

    monkeypatch.setattr(module, "_can_manage_transport", lambda: False)

    response = client.post("/staff/transport/5/schedule", data={}, follow_redirects=False)

    assert response.status_code == 302
    assert "/staff/attendance" in response.headers["Location"]


def test_schedule_updates_request_logs_and_redirects(client, monkeypatch):
    import routes.transport as module

    _login_staff(client, shelter="abba", staff_user_id=42)
    _force_session(client)

    cleanup_calls = []
    execute_calls = []
    log_calls = []

    monkeypatch.setattr(module, "_can_manage_transport", lambda: True)
    monkeypatch.setattr(module, "_cleanup_transport_requests", lambda s: cleanup_calls.append(s))
    monkeypatch.setattr(module, "utcnow_iso", lambda: "2026-04-15T10:00:00")

    def _fake_execute(sql, params):
        execute_calls.append((sql, params))

    monkeypatch.setattr(module, "db_execute", _fake_execute)
    monkeypatch.setattr(module, "log_action", lambda *args: log_calls.append(args))

    response = client.post(
        "/staff/transport/5/schedule",
        data={"staff_notes": "Driver assigned"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/staff/transport/pending")

    assert cleanup_calls == ["abba"]

    assert execute_calls
    _, params = execute_calls[0]

    assert params == (
        "scheduled",
        "2026-04-15T10:00:00",
        42,
        "Driver assigned",
        5,
        "abba",
        "pending",
    )

    assert log_calls == [
        ("transport", 5, "abba", 42, "approve", "Transport request approved")
    ]
