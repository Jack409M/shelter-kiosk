from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from flask import current_app, g, url_for


APP_TIMEZONE = ZoneInfo("America/Chicago")


def is_postgres() -> bool:
    db_kind = g.get("db_kind")
    if db_kind is not None:
        return db_kind == "pg"

    database_url = (current_app.config.get("DATABASE_URL") or "").strip()
    return bool(database_url)


def db_placeholder() -> str:
    if is_postgres():
        return "%s"
    return "?"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_datetime(value: Optional[str | datetime]) -> Optional[datetime]:
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None

        try:
            raw = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def to_app_tz(value: Optional[str | datetime]) -> Optional[datetime]:
    dt = _coerce_datetime(value)
    if not dt:
        return None
    return dt.astimezone(APP_TIMEZONE)


def fmt_date(dt_value: Optional[str | datetime]) -> str:
    dt = to_app_tz(dt_value)
    if not dt:
        return ""
    return dt.strftime("%m/%d/%Y")


def fmt_dt(dt_value: Optional[str | datetime]) -> str:
    dt = to_app_tz(dt_value)
    if not dt:
        return ""
    return dt.strftime("%m/%d/%Y %I:%M %p")


def fmt_time_only(dt_value: Optional[str | datetime]) -> str:
    dt = to_app_tz(dt_value)
    if not dt:
        return ""
    return dt.strftime("%I:%M %p")


def fmt_pretty_date(dt_value: Optional[str | datetime]) -> str:
    dt = to_app_tz(dt_value)
    if not dt:
        return ""
    return dt.strftime("%B %d, %Y")


def fmt_pretty_dt(dt_value: Optional[str | datetime]) -> str:
    dt = to_app_tz(dt_value)
    if not dt:
        return ""
    return dt.strftime("%B %d, %Y %I:%M %p")


def shelter_display(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    key = raw.lower()

    if key == "abba":
        return "Abba House"
    if key == "haven":
        return "Haven House"
    if key == "gratitude":
        return "Gratitude House"

    return raw


def safe_url_for(endpoint, **values):
    try:
        return url_for(endpoint, **values)
    except Exception:
        current_app.logger.error(f"URL BUILD ERROR: {endpoint} {values}")
        return "#"
