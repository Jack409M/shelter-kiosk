from __future__ import annotations

from datetime import datetime

from core.helpers import fmt_dt
from core.pass_retention import cleanup_deadline_from_expected_back
from core.time_utils import parse_utc_naive_datetime, utc_naive_iso


def test_parse_utc_naive_datetime_normalizes_aware_utc_string():
    parsed = parse_utc_naive_datetime("2026-05-02T12:00:00+00:00")

    assert parsed == datetime(2026, 5, 2, 12, 0, 0)
    assert parsed.tzinfo is None


def test_parse_utc_naive_datetime_treats_naive_input_as_utc():
    parsed = parse_utc_naive_datetime("2026-05-02T12:00:00")

    assert parsed == datetime(2026, 5, 2, 12, 0, 0)
    assert parsed.tzinfo is None


def test_parse_utc_naive_datetime_converts_chicago_offset_to_utc():
    parsed = parse_utc_naive_datetime("2026-05-02T07:00:00-05:00")

    assert parsed == datetime(2026, 5, 2, 12, 0, 0)
    assert parsed.tzinfo is None


def test_utc_naive_iso_strips_microseconds_and_timezone():
    normalized = utc_naive_iso("2026-05-02T07:00:00.123456-05:00")

    assert normalized == "2026-05-02T12:00:00"


def test_chicago_display_converts_internal_utc_naive_timestamp():
    assert fmt_dt("2026-05-02T12:00:00") == "05/02/2026 07:00 AM"


def test_pass_retention_deadline_accepts_aware_end_at():
    assert (
        cleanup_deadline_from_expected_back("2026-05-02T07:00:00-05:00", None)
        == "2026-05-04T12:00:00"
    )


def test_pass_retention_deadline_uses_chicago_end_date_cutoff():
    assert cleanup_deadline_from_expected_back(None, "2026-05-02") == "2026-05-05T04:59:59"
