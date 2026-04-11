from core.helpers import fmt_date, fmt_dt, fmt_time_only


def test_fmt_date_basic():
    assert fmt_date("2026-01-01T12:00:00") is not None


def test_fmt_dt_basic():
    assert fmt_dt("2026-01-01T12:00:00") is not None


def test_fmt_time_only_basic():
    assert fmt_time_only("2026-01-01T12:00:00") is not None
