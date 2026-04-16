from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest


@contextmanager
def _noop_transaction():
    yield


def test_normalize_and_clean_helpers():
    import core.kiosk_service as module

    assert module._normalize_shelter("  AbBa ") == "abba"
    assert module._normalize_shelter(None) == ""
    assert module._clean_text("  hello ") == "hello"
    assert module._clean_text(None) == ""


def test_parse_utc_datetime_handles_blank_invalid_naive_and_aware():
    import core.kiosk_service as module

    assert module._parse_utc_datetime(None) is None
    assert module._parse_utc_datetime("") is None
    assert module._parse_utc_datetime("bad") is None

    naive = module._parse_utc_datetime("2026-04-15T12:30:00")
    aware = module._parse_utc_datetime("2026-04-15T12:30:00+00:00")

    assert naive is not None
    assert aware is not None
    assert naive.tzinfo == UTC
    assert aware.tzinfo == UTC
    assert naive.isoformat() == "2026-04-15T12:30:00+00:00"
    assert aware.isoformat() == "2026-04-15T12:30:00+00:00"


def test_utc_iso_from_local_time_validates_inputs(monkeypatch):
    import core.kiosk_service as module

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 15, 9, 0, 0, tzinfo=tz)

    monkeypatch.setattr(module, "datetime", _FrozenDateTime)

    assert module._utc_iso_from_local_time("12", "15", "PM")
    assert module._utc_iso_from_local_time("12", "00", "AM")

    with pytest.raises(ValueError, match="Invalid hour"):
        module._utc_iso_from_local_time("13", "00", "AM")

    with pytest.raises(ValueError, match="Invalid minute"):
        module._utc_iso_from_local_time("10", "10", "AM")

    with pytest.raises(ValueError, match="Invalid AM or PM"):
        module._utc_iso_from_local_time("10", "15", "XX")


def test_active_resident_id_for_code_normalizes_inputs(monkeypatch):
    import core.kiosk_service as module

    seen: list[tuple[str, tuple[object, ...]]] = []

    def _fake_fetchone(sql, params):
        seen.append((sql, params))
        return {"id": 42}

    monkeypatch.setattr(module, "db_fetchone", _fake_fetchone)

    resident_id = module.active_resident_id_for_code(" AbBa ", " 12345678 ")

    assert resident_id == 42
    assert seen[0][1] == ("abba", "12345678")


def test_active_resident_id_for_code_returns_none_when_missing(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "db_fetchone", lambda sql, params: None)

    assert module.active_resident_id_for_code("abba", "12345678") is None


def test_latest_open_checkout_row_only_returns_check_out(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "db_fetchone", lambda sql, params: None)
    assert module.latest_open_checkout_row(5, "abba") is None

    monkeypatch.setattr(
        module,
        "db_fetchone",
        lambda sql, params: {"id": 1, "event_type": "check_in"},
    )
    assert module.latest_open_checkout_row(5, "abba") is None

    row = {
        "id": 2,
        "event_type": "check_out",
        "destination": "Work",
        "obligation_start_time": "2026-04-15T13:00:00",
        "obligation_end_time": "2026-04-15T14:00:00",
    }
    monkeypatch.setattr(module, "db_fetchone", lambda sql, params: row)
    assert module.latest_open_checkout_row(5, "abba") == row


def test_checkout_requires_actual_end_time_only_when_destination_and_window_present():
    import core.kiosk_service as module

    assert module.checkout_requires_actual_end_time(None) is False
    assert (
        module.checkout_requires_actual_end_time(
            {
                "destination": "",
                "obligation_start_time": "2026-04-15T13:00:00",
                "obligation_end_time": "2026-04-15T14:00:00",
            }
        )
        is False
    )
    assert (
        module.checkout_requires_actual_end_time(
            {
                "destination": "Work",
                "obligation_start_time": "2026-04-15T13:00:00",
                "obligation_end_time": "2026-04-15T14:00:00",
            }
        )
        is True
    )


def test_manual_time_value_delegates_to_local_converter(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "_utc_iso_from_local_time", lambda h, m, a: "2026-04-15T18:00:00")

    assert module.manual_time_value("6", "00", "PM") == "2026-04-15T18:00:00"


def test_active_pass_row_uses_normalized_shelter_and_current_dates(monkeypatch):
    import core.kiosk_service as module

    seen: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(module, "utcnow_iso", lambda: "2026-04-15T12:00:00")

    def _fake_fetchone(sql, params):
        seen.append((sql, params))
        return {"id": 7}

    monkeypatch.setattr(module, "db_fetchone", _fake_fetchone)

    row = module.active_pass_row(12, " AbBa ")

    assert row == {"id": 7}
    assert seen[0][1] == (
        12,
        "abba",
        "approved",
        "2026-04-15T12:00:00",
        "2026-04-15T12:00:00",
        "2026-04-15",
        "2026-04-15",
    )


def test_pass_expected_back_value_prefers_end_at_then_end_date():
    import core.kiosk_service as module

    assert (
        module.pass_expected_back_value({"end_at": "2026-04-15T21:00:00", "end_date": "2026-04-16"})
        == "2026-04-15T21:00:00"
    )

    derived = module.pass_expected_back_value({"end_at": "", "end_date": "2026-04-16"})
    assert derived is not None
    assert derived.startswith("2026-04-17T04:59:59") or derived.startswith("2026-04-16T")
    assert module.pass_expected_back_value({"end_at": "", "end_date": ""}) is None


def test_update_resident_rad_progress_noops_when_not_rad_or_no_resident(monkeypatch):
    import core.kiosk_service as module

    executed: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(module, "db_execute", lambda sql, params: executed.append((sql, params)))
    monkeypatch.setattr(module, "utcnow_iso", lambda: "2026-04-15T10:00:00")

    module.update_resident_rad_progress(0, "abba", "RAD")
    module.update_resident_rad_progress(5, "abba", "Work")

    assert executed == []


def test_update_resident_rad_progress_updates_when_destination_is_rad(monkeypatch):
    import core.kiosk_service as module

    executed: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(module, "db_execute", lambda sql, params: executed.append((sql, params)))
    monkeypatch.setattr(module, "utcnow_iso", lambda: "2026-04-15T10:00:00")

    module.update_resident_rad_progress(5, " AbBa ", " rad ")

    assert len(executed) == 1
    sql, params = executed[0]
    assert "UPDATE residents" in sql
    assert params == (True, False, "2026-04-15T10:00:00", 5, "abba")


def test_handle_checkin_rejects_bad_code_and_missing_resident(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: None)

    result = module.handle_checkin(
        shelter="abba",
        resident_code="12",
        actual_end_hour="",
        actual_end_minute="",
        actual_end_ampm="",
    )

    assert result.success is False
    assert result.status_code == 400
    assert "Enter an 8 digit Resident Code." in result.errors
    assert "Invalid Resident Code." in result.errors


def test_handle_checkin_prompts_for_actual_end_when_required(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 9)
    monkeypatch.setattr(
        module,
        "latest_open_checkout_row",
        lambda resident_id, shelter: {
            "id": 3,
            "destination": "Work",
            "obligation_start_time": "2026-04-15T13:00:00",
            "obligation_end_time": "2026-04-15T15:00:00",
        },
    )

    result = module.handle_checkin(
        shelter="abba",
        resident_code="12345678",
        actual_end_hour="",
        actual_end_minute="",
        actual_end_ampm="",
    )

    assert result.success is False
    assert result.status_code == 200
    assert result.actual_end_required is True
    assert result.needs_actual_end_prompt is True
    assert result.prior_activity_label == "Work"
    assert result.resident_id == 9


def test_handle_checkin_rejects_invalid_actual_end_time(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 9)
    monkeypatch.setattr(
        module,
        "latest_open_checkout_row",
        lambda resident_id, shelter: {
            "id": 3,
            "destination": "Work",
            "obligation_start_time": "2026-04-15T13:00:00",
            "obligation_end_time": "2026-04-15T15:00:00",
        },
    )
    monkeypatch.setattr(
        module,
        "manual_time_value",
        lambda h, m, a: (_ for _ in ()).throw(ValueError("bad")),
    )

    result = module.handle_checkin(
        shelter="abba",
        resident_code="12345678",
        actual_end_hour="1",
        actual_end_minute="15",
        actual_end_ampm="PM",
    )

    assert result.success is False
    assert result.status_code == 400
    assert result.errors == ["Invalid actual obligation end time."]


def test_handle_checkin_rejects_actual_end_before_start(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 9)
    monkeypatch.setattr(
        module,
        "latest_open_checkout_row",
        lambda resident_id, shelter: {
            "id": 3,
            "destination": "Work",
            "obligation_start_time": "2026-04-15T13:00:00",
            "obligation_end_time": "2026-04-15T15:00:00",
        },
    )
    monkeypatch.setattr(module, "utcnow_iso", lambda: "2026-04-15T18:00:00")
    monkeypatch.setattr(module, "manual_time_value", lambda h, m, a: "2026-04-15T12:00:00")

    result = module.handle_checkin(
        shelter="abba",
        resident_code="12345678",
        actual_end_hour="12",
        actual_end_minute="00",
        actual_end_ampm="PM",
    )

    assert result.success is False
    assert result.status_code == 400
    assert result.errors == ["Actual end time cannot be earlier than the scheduled start time."]


def test_handle_checkin_rejects_actual_end_after_checkin(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 9)
    monkeypatch.setattr(
        module,
        "latest_open_checkout_row",
        lambda resident_id, shelter: {
            "id": 3,
            "destination": "Work",
            "obligation_start_time": "2026-04-15T13:00:00",
            "obligation_end_time": "2026-04-15T15:00:00",
        },
    )
    monkeypatch.setattr(module, "utcnow_iso", lambda: "2026-04-15T18:00:00")
    monkeypatch.setattr(module, "manual_time_value", lambda h, m, a: "2026-04-15T19:00:00")

    result = module.handle_checkin(
        shelter="abba",
        resident_code="12345678",
        actual_end_hour="7",
        actual_end_minute="00",
        actual_end_ampm="PM",
    )

    assert result.success is False
    assert result.status_code == 400
    assert result.errors == ["Actual end time cannot be later than the time you are checking in."]


def test_handle_checkin_success_updates_open_checkout_and_inserts_checkin(monkeypatch):
    import core.kiosk_service as module
    import routes.attendance_parts.helpers as attendance_helpers

    executed: list[tuple[str, tuple[object, ...]]] = []
    completed: list[tuple[int, str]] = []

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 9)
    monkeypatch.setattr(
        module,
        "latest_open_checkout_row",
        lambda resident_id, shelter: {
            "id": 3,
            "destination": "Work",
            "obligation_start_time": "2026-04-15T13:00:00",
            "obligation_end_time": "2026-04-15T15:00:00",
        },
    )
    monkeypatch.setattr(module, "utcnow_iso", lambda: "2026-04-15T18:00:00")
    monkeypatch.setattr(module, "manual_time_value", lambda h, m, a: "2026-04-15T16:00:00")
    monkeypatch.setattr(module, "db_execute", lambda sql, params: executed.append((sql, params)))
    monkeypatch.setattr(module, "db_transaction", _noop_transaction)
    monkeypatch.setattr(
        attendance_helpers,
        "complete_active_passes",
        lambda resident_id, shelter: completed.append((resident_id, shelter)),
    )

    result = module.handle_checkin(
        shelter="abba",
        resident_code="12345678",
        actual_end_hour="4",
        actual_end_minute="00",
        actual_end_ampm="PM",
    )

    assert result.success is True
    assert result.status_code == 302
    assert result.actual_end_required is True
    assert result.prior_activity_label == "Work"
    assert result.log_note == "actual_obligation_end_time=2026-04-15T16:00:00"
    assert len(executed) == 2
    assert "UPDATE attendance_events" in executed[0][0]
    assert executed[0][1] == ("2026-04-15T16:00:00", 3, 9, "abba")
    assert "INSERT INTO attendance_events" in executed[1][0]
    assert completed == [(9, "abba")]


def test_handle_checkout_rejects_bad_code_and_missing_category(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: None)

    result = module.handle_checkout(
        shelter="abba",
        resident_code="12",
        destination="",
        aa_na_meeting_1="",
        aa_na_meeting_2="",
        volunteer_community_service_option="",
        start_time_hour="",
        start_time_minute="",
        start_time_ampm="",
        end_time_hour="",
        end_time_minute="",
        end_time_ampm="",
        expected_back_hour="",
        expected_back_minute="",
        expected_back_ampm="",
        note="",
        checkout_categories=[],
        aa_na_child_options=[],
        volunteer_child_options=[],
        aa_na_parent_activity_key="aa_na",
        volunteer_parent_activity_key="volunteer",
    )

    assert result.success is False
    assert "Enter an 8 digit Resident Code." in result.errors
    assert "Activity Category is required." in result.errors
    assert "Invalid Resident Code." in result.errors


def test_handle_checkout_rejects_invalid_category(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 11)

    result = module.handle_checkout(
        shelter="abba",
        resident_code="12345678",
        destination="Unknown",
        aa_na_meeting_1="",
        aa_na_meeting_2="",
        volunteer_community_service_option="",
        start_time_hour="",
        start_time_minute="",
        start_time_ampm="",
        end_time_hour="",
        end_time_minute="",
        end_time_ampm="",
        expected_back_hour="",
        expected_back_minute="",
        expected_back_ampm="",
        note="",
        checkout_categories=[],
        aa_na_child_options=[],
        volunteer_child_options=[],
        aa_na_parent_activity_key="aa_na",
        volunteer_parent_activity_key="volunteer",
    )

    assert result.success is False
    assert "Please select a valid Activity Category." in result.errors
    assert "Start Time is required." in result.errors
    assert "End Time is required." in result.errors
    assert "Expected Back to Shelter is required." in result.errors


def test_handle_checkout_validates_aa_na_options(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 11)

    categories = [
        {
            "activity_label": "AA or NA Meeting",
            "activity_key": "aa_na",
            "requires_approved_pass": False,
        }
    ]
    aa_options = [{"option_label": "Morning"}, {"option_label": "Evening"}]

    result = module.handle_checkout(
        shelter="abba",
        resident_code="12345678",
        destination="AA or NA Meeting",
        aa_na_meeting_1="Morning",
        aa_na_meeting_2="Morning",
        volunteer_community_service_option="",
        start_time_hour="1",
        start_time_minute="00",
        start_time_ampm="PM",
        end_time_hour="2",
        end_time_minute="00",
        end_time_ampm="PM",
        expected_back_hour="3",
        expected_back_minute="00",
        expected_back_ampm="PM",
        note="",
        checkout_categories=categories,
        aa_na_child_options=aa_options,
        volunteer_child_options=[],
        aa_na_parent_activity_key="aa_na",
        volunteer_parent_activity_key="volunteer",
    )

    assert result.success is False
    assert "Meeting 1 and Meeting 2 cannot be the same." in result.errors


def test_handle_checkout_validates_volunteer_option(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 11)

    categories = [
        {
            "activity_label": "Volunteer",
            "activity_key": "volunteer",
            "requires_approved_pass": False,
        }
    ]

    result = module.handle_checkout(
        shelter="abba",
        resident_code="12345678",
        destination="Volunteer",
        aa_na_meeting_1="",
        aa_na_meeting_2="",
        volunteer_community_service_option="",
        start_time_hour="1",
        start_time_minute="00",
        start_time_ampm="PM",
        end_time_hour="2",
        end_time_minute="00",
        end_time_ampm="PM",
        expected_back_hour="3",
        expected_back_minute="00",
        expected_back_ampm="PM",
        note="",
        checkout_categories=categories,
        aa_na_child_options=[],
        volunteer_child_options=[{"option_label": "Community Service"}],
        aa_na_parent_activity_key="aa_na",
        volunteer_parent_activity_key="volunteer",
    )

    assert result.success is False
    assert result.errors == ["Volunteer or Community Service selection is required."]


def test_handle_checkout_requires_approved_pass_when_category_demands_it(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 11)
    monkeypatch.setattr(module, "active_pass_row", lambda resident_id, shelter: None)

    categories = [
        {
            "activity_label": "Pass Activity",
            "activity_key": "pass_activity",
            "requires_approved_pass": True,
        }
    ]

    result = module.handle_checkout(
        shelter="abba",
        resident_code="12345678",
        destination="Pass Activity",
        aa_na_meeting_1="",
        aa_na_meeting_2="",
        volunteer_community_service_option="",
        start_time_hour="",
        start_time_minute="",
        start_time_ampm="",
        end_time_hour="",
        end_time_minute="",
        end_time_ampm="",
        expected_back_hour="",
        expected_back_minute="",
        expected_back_ampm="",
        note="",
        checkout_categories=categories,
        aa_na_child_options=[],
        volunteer_child_options=[],
        aa_na_parent_activity_key="aa_na",
        volunteer_parent_activity_key="volunteer",
    )

    assert result.success is False
    assert result.errors == ["No approved pass found for that Activity Category."]


def test_handle_checkout_rejects_invalid_manual_times(monkeypatch):
    import core.kiosk_service as module

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 11)

    categories = [
        {
            "activity_label": "Work",
            "activity_key": "work",
            "requires_approved_pass": False,
        }
    ]

    def _manual_time_value(hour_text, minute_text, ampm_text):
        if hour_text == "bad":
            raise ValueError("bad")
        return "2026-04-15T13:00:00"

    monkeypatch.setattr(module, "manual_time_value", _manual_time_value)

    result = module.handle_checkout(
        shelter="abba",
        resident_code="12345678",
        destination="Work",
        aa_na_meeting_1="",
        aa_na_meeting_2="",
        volunteer_community_service_option="",
        start_time_hour="bad",
        start_time_minute="00",
        start_time_ampm="PM",
        end_time_hour="2",
        end_time_minute="00",
        end_time_ampm="PM",
        expected_back_hour="3",
        expected_back_minute="00",
        expected_back_ampm="PM",
        note="",
        checkout_categories=categories,
        aa_na_child_options=[],
        volunteer_child_options=[],
        aa_na_parent_activity_key="aa_na",
        volunteer_parent_activity_key="volunteer",
    )

    assert result.success is False
    assert "Invalid Start Time." in result.errors


def test_handle_checkout_success_with_manual_times_and_rad_progress(monkeypatch):
    import core.kiosk_service as module

    executed: list[tuple[str, tuple[object, ...]]] = []
    rad_updates: list[tuple[int, str, str | None]] = []

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 11)
    monkeypatch.setattr(module, "db_transaction", _noop_transaction)
    monkeypatch.setattr(module, "utcnow_iso", lambda: "2026-04-15T12:00:00")
    monkeypatch.setattr(
        module,
        "manual_time_value",
        lambda hour_text, minute_text, ampm_text: {
            ("1", "00", "PM"): "2026-04-15T13:00:00",
            ("2", "00", "PM"): "2026-04-15T14:00:00",
            ("3", "00", "PM"): "2026-04-15T15:00:00",
        }[(hour_text, minute_text, ampm_text)],
    )
    monkeypatch.setattr(module, "db_execute", lambda sql, params: executed.append((sql, params)))
    monkeypatch.setattr(
        module,
        "update_resident_rad_progress",
        lambda resident_id, shelter, destination_label: rad_updates.append(
            (resident_id, shelter, destination_label)
        ),
    )

    categories = [
        {
            "activity_label": "RAD",
            "activity_key": "rad",
            "requires_approved_pass": False,
        }
    ]

    result = module.handle_checkout(
        shelter="abba",
        resident_code="12345678",
        destination="RAD",
        aa_na_meeting_1="",
        aa_na_meeting_2="",
        volunteer_community_service_option="",
        start_time_hour="1",
        start_time_minute="00",
        start_time_ampm="PM",
        end_time_hour="2",
        end_time_minute="00",
        end_time_ampm="PM",
        expected_back_hour="3",
        expected_back_minute="00",
        expected_back_ampm="PM",
        note="Bring notebook",
        checkout_categories=categories,
        aa_na_child_options=[],
        volunteer_child_options=[],
        aa_na_parent_activity_key="aa_na",
        volunteer_parent_activity_key="volunteer",
    )

    assert result.success is True
    assert result.status_code == 302
    assert result.resident_id == 11
    assert result.destination_value == "RAD"
    assert result.selected_activity_key == "rad"
    assert result.obligation_start_value == "2026-04-15T13:00:00"
    assert result.obligation_end_value == "2026-04-15T14:00:00"
    assert result.expected_back_value == "2026-04-15T15:00:00"
    assert len(executed) == 1
    assert "INSERT INTO attendance_events" in executed[0][0]
    assert "Activity Category: RAD" in executed[0][1][5]
    assert "Bring notebook" in executed[0][1][5]
    assert rad_updates == [(11, "abba", "RAD")]


def test_handle_checkout_success_with_pass_and_aa_meetings(monkeypatch):
    import core.kiosk_service as module

    executed: list[tuple[str, tuple[object, ...]]] = []

    monkeypatch.setattr(module, "active_resident_id_for_code", lambda shelter, code: 11)
    monkeypatch.setattr(module, "db_transaction", _noop_transaction)
    monkeypatch.setattr(module, "utcnow_iso", lambda: "2026-04-15T12:00:00")
    monkeypatch.setattr(
        module,
        "active_pass_row",
        lambda resident_id, shelter: {
            "id": 99,
            "pass_type": "Overnight Pass",
            "destination": "Family Visit",
            "end_at": "2026-04-15T22:00:00",
            "end_date": "",
        },
    )
    monkeypatch.setattr(module, "pass_expected_back_value", lambda pass_row: "2026-04-15T22:00:00")
    monkeypatch.setattr(module, "db_execute", lambda sql, params: executed.append((sql, params)))
    monkeypatch.setattr(module, "update_resident_rad_progress", lambda **kwargs: None)

    categories = [
        {
            "activity_label": "AA or NA Meeting",
            "activity_key": "aa_na",
            "requires_approved_pass": True,
        }
    ]
    aa_options = [{"option_label": "Morning"}, {"option_label": "Evening"}]

    result = module.handle_checkout(
        shelter="abba",
        resident_code="12345678",
        destination="AA or NA Meeting",
        aa_na_meeting_1="Morning",
        aa_na_meeting_2="Evening",
        volunteer_community_service_option="",
        start_time_hour="",
        start_time_minute="",
        start_time_ampm="",
        end_time_hour="",
        end_time_minute="",
        end_time_ampm="",
        expected_back_hour="",
        expected_back_minute="",
        expected_back_ampm="",
        note="",
        checkout_categories=categories,
        aa_na_child_options=aa_options,
        volunteer_child_options=[],
        aa_na_parent_activity_key="aa_na",
        volunteer_parent_activity_key="volunteer",
    )

    assert result.success is True
    assert result.meeting_count == 2
    assert result.is_recovery_meeting_value == 1
    assert result.expected_back_value == "2026-04-15T22:00:00"
    assert result.obligation_start_value is None
    assert result.obligation_end_value is None
    assert len(executed) == 1
    note_value = executed[0][1][5]
    assert "Meeting 1: Morning" in note_value
    assert "Meeting 2: Evening" in note_value
    assert "Pass ID: 99" in note_value
    assert "Pass Type: Overnight Pass" in note_value
    assert "Pass Destination: Family Visit" in note_value
