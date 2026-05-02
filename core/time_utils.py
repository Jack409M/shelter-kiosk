from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

CHICAGO_TZ = ZoneInfo("America/Chicago")


def parse_utc_naive_datetime(value: datetime | str | None) -> datetime | None:
    """Parse timestamp-like values into naive UTC datetimes.

    The app stores internal timestamps as UTC without tzinfo. A naive input is
    therefore treated as UTC, while aware inputs are converted to UTC first.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)

    return parsed.replace(microsecond=0)


def utc_naive_iso(value: datetime | str | None) -> str | None:
    parsed = parse_utc_naive_datetime(value)
    if parsed is None:
        return None
    return parsed.isoformat(timespec="seconds")


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def to_chicago(value: datetime | str | None) -> datetime | None:
    parsed = parse_utc_naive_datetime(value)
    if parsed is None:
        return None
    return parsed.replace(tzinfo=UTC).astimezone(CHICAGO_TZ)
