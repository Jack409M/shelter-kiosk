from __future__ import annotations

import os

from flask import g

from core.db import db_execute, db_fetchone
from core.sms import sms_is_allowed_for_number

try:
    from twilio.rest import Client
except Exception:
    Client = None


TWILIO_ENABLED = os.environ.get("TWILIO_ENABLED", "false").lower() == "true"
TWILIO_STATUS_ENABLED = os.environ.get("TWILIO_STATUS_ENABLED", "false").strip().lower() == "true"
TWILIO_STATUS_CALLBACK_URL = (os.environ.get("TWILIO_STATUS_CALLBACK_URL") or "").strip()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")


def _normalize_to_e164(to_number: str) -> str | None:
    raw = (to_number or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())

    if raw.startswith("+"):
        return raw
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None


def _rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    """
    Lightweight DB backed rate limiter.

    Uses Postgres table when available.
    Falls back to allowing sends if db kind is not pg because the
    current app logic only calls this in production Postgres paths.
    """
    if g.get("db_kind") != "pg":
        return False

    if limit <= 0 or window_seconds <= 0:
        return True

    db_execute(
        "INSERT INTO rate_limit_events (k) VALUES (%s)",
        (key,),
    )

    row = db_fetchone(
        """
        SELECT COUNT(1) AS c
        FROM rate_limit_events
        WHERE k = %s
          AND created_at >= NOW() - (%s * INTERVAL '1 second')
        """,
        (key, window_seconds),
    )
    count = int(row["c"] if isinstance(row, dict) else row[0])
    return count > limit


def send_sms(to_number: str, message: str, enforce_consent: bool = True) -> None:
    """
    Outbound SMS sender with:
    global panic switch,
    Twilio enable gate,
    optional consent enforcement,
    per number and global rate limiting.
    """
    if os.environ.get("SMS_SYSTEM_ENABLED", "true").lower() != "true":
        return

    if not TWILIO_ENABLED:
        return

    if enforce_consent:
        try:
            if not sms_is_allowed_for_number(to_number):
                return
        except Exception:
            return

    if not Client:
        return

    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
        return

    to_e164 = _normalize_to_e164(to_number)
    if not to_e164:
        return

    try:
        per_number_per_hour = int(os.environ.get("SMS_OUTBOUND_PER_NUMBER_PER_HOUR", "6"))
    except Exception:
        per_number_per_hour = 6

    try:
        global_per_minute = int(os.environ.get("SMS_OUTBOUND_GLOBAL_PER_MIN", "30"))
    except Exception:
        global_per_minute = 30

    from core.sms import _normalize_us_phone_10

    to10 = _normalize_us_phone_10(to_e164) or to_e164

    if _rate_limited("sms_out_global", global_per_minute, 60):
        return

    if _rate_limited(f"sms_out_to:{to10}", per_number_per_hour, 3600):
        return

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        kwargs = {"body": message, "from_": TWILIO_FROM_NUMBER, "to": to_e164}
        if TWILIO_STATUS_ENABLED and TWILIO_STATUS_CALLBACK_URL:
            kwargs["status_callback"] = TWILIO_STATUS_CALLBACK_URL

        client.messages.create(**kwargs)
    except Exception as e:
        print("SMS error:", e)
