from __future__ import annotations

from typing import Optional

from flask import current_app

from core.db import db_fetchall


def _init_db() -> None:
    """
    Run the configured database initializer.

    The app should store the callable in:
        app.config["INIT_DB_FUNC"]

    This avoids importing app directly and prevents circular import problems.
    """
    init_func = current_app.config.get("INIT_DB_FUNC")
    if callable(init_func):
        init_func()
        return

    raise RuntimeError("INIT_DB_FUNC is not configured")


def _normalize_us_phone_10(phone: str) -> Optional[str]:
    """
    Normalize a phone number down to a 10 digit US number when possible.

    Examples
    8065551212         -> 8065551212
    18065551212        -> 8065551212
    +1 (806) 555 1212  -> 8065551212

    Returns None when the input cannot be normalized to a usable US number.
    """
    raw = (phone or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())

    if len(digits) == 10:
        return digits

    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]

    if len(digits) > 11:
        return digits[-10:]

    return None


def sms_is_allowed_for_number(phone: str) -> bool:
    """
    Allow SMS only when the matching resident record shows:

    1. sms_opt_in is true
    2. sms_opt_out_at is empty

    This function fails closed. If anything goes wrong, it returns False.
    """
    try:
        _init_db()
    except Exception:
        return False

    target = _normalize_us_phone_10(phone)
    if not target:
        return False

    try:
        rows = db_fetchall(
            """
            SELECT phone, sms_opt_in, sms_opt_out_at
            FROM residents
            WHERE phone IS NOT NULL AND phone != ''
            ORDER BY id DESC
            LIMIT 300
            """
        )
    except Exception:
        return False

    for row in rows or []:
        resident_phone = row["phone"] if isinstance(row, dict) else row[0]
        resident_opt_in = row["sms_opt_in"] if isinstance(row, dict) else row[1]
        resident_opt_out_at = row["sms_opt_out_at"] if isinstance(row, dict) else row[2]

        if _normalize_us_phone_10(str(resident_phone or "")) != target:
            continue

        if not bool(resident_opt_in):
            return False

        if resident_opt_out_at:
            return False

        return True

    return False
