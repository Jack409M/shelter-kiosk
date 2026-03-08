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
