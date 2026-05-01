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


def _log_sms_attempt(
    *,
    to_number_raw: str,
    to_number_e164: str | None,
    status: str,
    reason: str,
    twilio_sid: str | None = None,
    enforce_consent: bool = True,
) -> None:
    """
    Best effort outbound SMS attempt logger.

    Logging must never block the actual send path. If the table does not exist
    yet during deployment startup, the sender still returns the correct send
    result and future attempts will log after schema init runs.
    """
    try:
        db_execute(
            """
            INSERT INTO sms_attempt_log
            (
                to_number_raw,
                to_number_e164,
                status,
                reason,
                twilio_sid,
                enforce_consent,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, NOW())
            """,
            (
                to_number_raw,
                to_number_e164,
                status,
                reason[:500] if reason else None,
                twilio_sid,
                bool(enforce_consent),
            ),
        )
    except Exception:
        return


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


def sms_delivery_ready() -> tuple[bool, str]:
    if os.environ.get("SMS_SYSTEM_ENABLED", "true").lower() != "true":
        return False, "SMS_SYSTEM_ENABLED is not true"

    if not TWILIO_ENABLED:
        return False, "TWILIO_ENABLED is not true"

    if not Client:
        return False, "Twilio client library is not available"

    missing = []
    if not TWILIO_ACCOUNT_SID:
        missing.append("TWILIO_ACCOUNT_SID")
    if not TWILIO_AUTH_TOKEN:
        missing.append("TWILIO_AUTH_TOKEN")
    if not TWILIO_FROM_NUMBER:
        missing.append("TWILIO_FROM_NUMBER")

    if missing:
        return False, "Missing " + ", ".join(missing)

    return True, "ready"


def send_sms(to_number: str, message: str, enforce_consent: bool = True) -> bool:
    """
    Outbound SMS sender with:
    global panic switch,
    Twilio enable gate,
    optional consent enforcement,
    per number and global rate limiting.

    Returns True when a Twilio send was attempted successfully and False when
    the message was skipped or failed.
    """
    ready, reason = sms_delivery_ready()
    if not ready:
        _log_sms_attempt(
            to_number_raw=to_number,
            to_number_e164=None,
            status="skipped",
            reason=reason,
            enforce_consent=enforce_consent,
        )
        return False

    if enforce_consent:
        try:
            if not sms_is_allowed_for_number(to_number):
                _log_sms_attempt(
                    to_number_raw=to_number,
                    to_number_e164=None,
                    status="skipped",
                    reason="SMS consent not found or not allowed",
                    enforce_consent=enforce_consent,
                )
                return False
        except Exception as exc:
            _log_sms_attempt(
                to_number_raw=to_number,
                to_number_e164=None,
                status="failed",
                reason=f"SMS consent check failed: {exc}",
                enforce_consent=enforce_consent,
            )
            return False

    to_e164 = _normalize_to_e164(to_number)
    if not to_e164:
        _log_sms_attempt(
            to_number_raw=to_number,
            to_number_e164=None,
            status="failed",
            reason="Invalid destination phone number",
            enforce_consent=enforce_consent,
        )
        return False

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
        _log_sms_attempt(
            to_number_raw=to_number,
            to_number_e164=to_e164,
            status="skipped",
            reason="Global SMS rate limit reached",
            enforce_consent=enforce_consent,
        )
        return False

    if _rate_limited(f"sms_out_to:{to10}", per_number_per_hour, 3600):
        _log_sms_attempt(
            to_number_raw=to_number,
            to_number_e164=to_e164,
            status="skipped",
            reason="Per number SMS rate limit reached",
            enforce_consent=enforce_consent,
        )
        return False

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        kwargs = {"body": message, "from_": TWILIO_FROM_NUMBER, "to": to_e164}
        if TWILIO_STATUS_ENABLED and TWILIO_STATUS_CALLBACK_URL:
            kwargs["status_callback"] = TWILIO_STATUS_CALLBACK_URL

        twilio_message = client.messages.create(**kwargs)
        _log_sms_attempt(
            to_number_raw=to_number,
            to_number_e164=to_e164,
            status="sent",
            reason="ok",
            twilio_sid=getattr(twilio_message, "sid", None),
            enforce_consent=enforce_consent,
        )
        return True
    except Exception as exc:
        _log_sms_attempt(
            to_number_raw=to_number,
            to_number_e164=to_e164,
            status="failed",
            reason=f"Twilio send failed: {exc}",
            enforce_consent=enforce_consent,
        )
        print("SMS error:", exc)
        return False
