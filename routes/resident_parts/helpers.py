from __future__ import annotations

from datetime import datetime


# Resident request shared helpers
#
# Future extraction note
# This file should hold small shared helpers used by multiple resident
# request flows, especially parsing and common validation utilities.
#
# Likely future additions:
# common session readers
# common rate limit key builders
# shared resident context loaders


def parse_dt(dt_str: str) -> datetime:
    text = (dt_str or "").strip()
    if not text:
        raise ValueError("datetime input is required")

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    return datetime.strptime(text, "%Y-%m-%d %I:%M %p")
