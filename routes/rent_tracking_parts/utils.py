from __future__ import annotations

from flask import g


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _float_value(value) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return round(float(value), 2)
    except Exception:
        return 0.0


def _int_value(value, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def _bool_value(value) -> bool:
    if isinstance(value, bool):
        return value
    return value in (1, "1", "true", "True", "yes", "Yes", "on")
