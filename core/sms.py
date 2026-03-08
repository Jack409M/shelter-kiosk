from __future__ import annotations

import os
from typing import Optional

from flask import g

from core.db import db_fetchall

def _normalize_us_phone_10(phone: str) -> Optional[str]:
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
    Allow SMS only if the resident has opted in and has not opted out.
    """
    from app import init_db

    init_db()

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
        r_phone = row["phone"] if isinstance(row, dict) else row[0]
        r_opt_in = row["sms_opt_in"] if isinstance(row, dict) else row[1]
        r_opt_out_at = row["sms_opt_out_at"] if isinstance(row, dict) else row[2]

        if _normalize_us_phone_10(str(r_phone or "")) != target:
            continue

        if not bool(r_opt_in):
            return False

        if r_opt_out_at:
            return False

        return True

    return False
