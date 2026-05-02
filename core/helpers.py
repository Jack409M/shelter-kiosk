from __future__ import annotations

import os

from core.time_utils import to_chicago, utcnow_iso  # noqa: F401

# ============================================================================
# Timezone
# ============================================================================


def _to_chi(dt):
    return to_chicago(dt)


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
