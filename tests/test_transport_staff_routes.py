from __future__ import annotations

from datetime import datetime

import pytest


def _login_staff(client, *, shelter: str = "abba", staff_user_id: int = 7) -> None:
    with client.session_transaction() as session:
        session["role"] = "staff"
        session["username"] = "staffuser"
        session["staff_user_id"] = staff_user_id
        session["shelter"] = shelter


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

    monkeypatch.setattr(module, "_can_manage_transport", lambda: False)

    response = client.get("/staff/transport/pending", follow_redirects=False)

    assert response.status_code == 302
    assert "/staff/login" in response.headers["Location"]


def test_pending_renders_rows_for_shelter(client, monkeypatch):
    import routes.transport as module

    _login_staff(client, shelter="abba")

    cleanup_calls: list[str] = []
    query_calls: list[tuple[str, tuple[object, ...]]] = []

    monkeypatch.setattr(module, "_can_manage_transport", lambda: True)
    monkeypatch.setattr(module, "_cleanup_transport_requests", lambda shelter: cleanup_calls.append(shelter))

    fake_rows = [
        {
            "id": 1,
            "needed_at": "2026-04-15T14:00:00+00:00",
            "first_name": "Jane",
            "last_name": "Doe",
            "pickup_location": "Shelter",
            "destination": "Clinic",
            "status": "pending",
        }
    ]

    def _fake_fetchall(sql, params):
        query_calls.append((sql, params))
        return fake_rows

    monkeypatch.setattr(module, "db_fetchall", _fake_fetchall)

    response = client.get("/staff/transport/pending", follow_redirects=True)

    assert response.status_code == 200
    assert cleanup_calls == ["abba"]
    assert query_calls[0][1] == ("pending", "abba")
    assert b"Jane" in response.data or b"Doe" in response.data


def test_board_filters_rows_by_local_day(client, monkeypatch):
    import routes.transport as module

    _login_staff(client, shelter="abba")

    monkeypatch.setattr(module, "_can_manage_transport", lambda: True)
    monkeypatch.setattr(module, "_cleanup_transport_requests", lambda shelter: None)

    fake_rows = [
        {
            "id": 1,
            "needed_at": "2026-04-15T14:00:00+00:00",
            "first_name": "Jane",
            "last_name": "Doe",
            "pickup_location": "Shelter",
            "destination": "Clinic",
            "status": "pending",
        },
        {
            "id": 2,
            "needed_at": "2026-04-16T14:00:00+00:00",
            "first_name": "Amy",
            "last_name": "Smith",
            "pickup_location": "House",
            "destination": "Office",
            "status": "scheduled",
        },
    ]

    monkeypatch.setattr(module, "db_fetchall", lambda sql, params: fake_rows)

    response = client.get("/staff/transport/board?date=2026-04-15", follow_redirects=True)

    assert response.status_code == 200
    assert b"Jane" in response.data or b"Doe" in response.data
    assert b"Amy" not in response.data
    assert b"Smith" not in response.data


def test_print_defaults_to_today_and_shows_no_rides_message(client, monkeypatch):
    import routes.transport as module

    _login_staff(client, shelter="abba")

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 15, 9, 0, 0, tzinfo=tz)

    monkeypatch.setattr(module, "_can_manage_transport", lambda: True)
    monkeypatch.setattr(module, "_cleanup_transport_requests", lambda shelter: None)
    monkeypatch.setattr(module, "db_fetchall", lambda sql, params: [])
    monkeypatch.setattr(module, "datetime", _FrozenDateTime)

    response = client.get("/staff/transport/print", follow_redirects=True)

    assert response.status_code == 200
    assert b"Transportation Sheet" in response.data
    assert b"2026-04-15" in response.data
    assert b"No rides found." in response.data


def test_print_renders_filtered_rows_and_escapes_html(client, monkeypatch):
    import routes.transport as module

    _login_staff(client, shelter="abba")

    monkeypatch.setattr(module, "_can_manage_transport", lambda: True)
    monkeypatch.setattr(module, "_cleanup_transport_requests", lambda shelter: None)

    fake_rows = [
        {
            "id": 1,
            "needed_at": "2026-04-15T14:00:00+00:00",
            "first_name": "Jane<script>",
            "last_name": "Doe",
            "pickup_location": "Shelter & Hall",
            "destination": "Clinic",
            "status": "pending",
        },
        {
            "id": 2,
            "needed_at": "2026-04-16T14:00:00+00:00",
            "first_name": "Amy",
            "last_name": "Smith",
            "pickup_location": "House",
            "destination": "Office",
            "status": "scheduled",
        },
    ]

    monkeypatch.setattr(module, "db_fetchall", lambda sql, params: fake_rows)

    response = client.get("/staff/transport/print?date=2026-04-15", follow_redirects=True)

    assert response.status_code == 200
    assert b"Jane&lt;script&gt;" in response.data
    assert b"Shelter &amp; Hall" in response.data
    assert b"Amy" not in response.data
    assert b"Smith" not in response.data


def test_schedule_requires_permission(client, monkeypatch):
    import routes.transport as module

    _login_staff(client)

    monkeypatch.setattr(module, "_can_manage_transport", lambda: False)

    response = client.post("/staff/transport/5/schedule", data={}, follow_redirects=False)

    assert response.status_code == 302
    assert "/staff/login" in response.headers["Location"]


def test_schedule_updates_request_logs_and_redirects(client, monkeypatch):
    import routes.transport as module

    _login_staff(client, shelter="abba", staff_user_id=42)

    cleanup_calls: list[str] = []
    execute_calls: list[tuple[str, tuple[object, ...]]] = []
    log_calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(module, "_can_manage_transport", lambda: True)
    monkeypatch.setattr(module, "_cleanup_transport_requests", lambda shelter: cleanup_calls.append(shelter))
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
    sql, params = execute_calls[0]
    assert "UPDATE transport_requests" in sql
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


@pytest.mark.parametrize("db_kind", ["pg", "sqlite"])
def test_cleanup_transport_requests_uses_expected_sql_placeholder(monkeypatch, db_kind):
    import routes.transport as module

    executed: list[tuple[str, tuple[object, ...]]] = []

    monkeypatch.setattr(module, "db_execute", lambda sql, params: executed.append((sql, params)))

    class _FakeG:
        def get(self, key, default=None):
            if key == "db_kind":
                return db_kind
            return default

    monkeypatch.setattr(module, "g", _FakeG())

    module._cleanup_transport_requests("abba")

    assert len(executed) == 2
    first_sql, first_params = executed[0]
    second_sql, second_params = executed[1]

    if db_kind == "pg":
        assert "%s" in first_sql
        assert "%s" in second_sql
    else:
        assert "?" in first_sql
        assert "?" in second_sql

    assert first_params[0] == "abba"
    assert first_params[1] == "pending"
    assert second_params[0] == "abba"
    assert second_params[1] == "scheduled"
