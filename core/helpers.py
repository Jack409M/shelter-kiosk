from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ============================================================================
# Timezone
# ============================================================================

CHI = ZoneInfo("America/Chicago")


def _to_chi(dt: datetime | str | None) -> datetime | None:
    if not dt:
        return None

    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(CHI)


# ============================================================================
# Formatting (Chicago time everywhere)
# ============================================================================

def fmt_dt(value) -> str:
    dt = _to_chi(value)
    if not dt:
        return "—"
    return dt.strftime("%m/%d/%Y %I:%M %p")


def fmt_date(value) -> str:
    dt = _to_chi(value)
    if not dt:
        return "—"
    return dt.strftime("%m/%d/%Y")


def fmt_time_only(value) -> str:
    dt = _to_chi(value)
    if not dt:
        return "—"
    return dt.strftime("%I:%M %p")


def fmt_pretty_dt(value) -> str:
    dt = _to_chi(value)
    if not dt:
        return "—"
    return dt.strftime("%b %d, %Y at %I:%M %p")


def fmt_pretty_date(value) -> str:
    dt = _to_chi(value)
    if not dt:
        return "—"
    return dt.strftime("%b %d, %Y")


# ============================================================================
# REQUIRED EXISTING FUNCTIONS (DO NOT REMOVE)
# ============================================================================

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_postgres() -> bool:
    return bool((os.getenv("DATABASE_URL") or "").strip())


def safe_url_for(endpoint: str, **values) -> str:
    from flask import url_for
    try:
        return url_for(endpoint, **values)
    except Exception:
        return "#"


def shelter_display(name: str | None) -> str:
    if not name:
        return "—"
    return name.replace("_", " ").title()
