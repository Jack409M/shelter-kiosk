from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from flask import g


def is_postgres():
    return g.get("db_kind") == "pg"


def db_placeholder():
    if g.get("db_kind") == "pg":
        return "%s"
    return "?"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fmt_date(dt_iso: Optional[str]) -> str:
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(dt_iso)
        dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo("America/Chicago"))
        return local_dt.strftime("%m/%d/%Y")
    except Exception:
        return dt_iso


def fmt_dt(dt_iso: Optional[str]) -> str:
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(dt_iso)
        dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo("America/Chicago"))
        return local_dt.strftime("%m/%d/%Y %I:%M %p")
    except Exception:
        return dt_iso


def fmt_time_only(dt_iso: Optional[str]) -> str:
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(dt_iso)
        dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo("America/Chicago"))
        return local_dt.strftime("%I:%M %p")
    except Exception:
        return ""


def fmt_pretty_date(dt_iso: Optional[str]) -> str:
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(dt_iso)
        dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo("America/Chicago"))
        return local_dt.strftime("%B %d, %Y")
    except Exception:
        return dt_iso
