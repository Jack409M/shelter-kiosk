from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from zoneinfo import ZoneInfo


CHICAGO_TZ = ZoneInfo("America/Chicago")


def _today_chicago() -> datetime:
    return datetime.now(CHICAGO_TZ)


def _current_year_month() -> tuple[int, int]:
    now = _today_chicago()
    return now.year, now.month


def _month_label(year: int, month: int) -> str:
    return datetime(year, month, 1).strftime("%B %Y")


def _parse_iso_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


def _month_start_end(year: int, month: int) -> tuple[date, date]:
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _days_in_month(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = (year * 12 + (month - 1)) + delta
    shifted_year = month_index // 12
    shifted_month = (month_index % 12) + 1
    return shifted_year, shifted_month


def _completed_month_keys(lookback_months: int = 9) -> list[tuple[int, int]]:
    current_year, current_month = _current_year_month()
    months: list[tuple[int, int]] = []
    for offset in range(1, lookback_months + 1):
        months.append(_shift_month(current_year, current_month, -offset))
    return months
