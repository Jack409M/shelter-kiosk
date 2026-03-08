from __future__ import annotations

import os

from flask import Blueprint, abort, current_app, g, request

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso

try:
    from twilio.request_validator import RequestValidator
except Exception:
    RequestValidator = None


twilio = Blueprint("twilio", __name__)


def _client_ip() -> str:
    return (request.remote_addr or "").strip() or "unknown"


def _rate_limited_memory_store() -> dict:
    store = current_app.config.setdefault("_RATE_BUCKETS_MEM", {})
    return store


def _rate_limited_memory(key: str, limit: int, window_seconds: int) -> bool:
    import time
    from collections import deque

    now = time.time()
    buckets = _rate_limited_memory_store()
    bucket = buckets.get(key)

    if bucket is None:
        bucket = deque()
        buckets[key] = bucket

    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if len(bucket) >= limit:
        return True

    bucket.append(now)
    return False


def _rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    import time

    if g.get("db_kind") != "pg":
        return _rate_limited_memory(key, limit, window_seconds)

    if limit <= 0 or window_seconds <= 0:
        return True

    db_execute(
        "INSERT INTO rate_limit_events (k) VALUES (%s)",
        (key,),
    )

    rows = db_fetchall(
        """
        SELECT COUNT(1) AS c
        FROM rate_limit_events
        WHERE k = %s
          AND created_at >= NOW() - (%s * INTERVAL '1 second')
        """,
        (key, window_seconds),
    )
    c = int((rows[0]["c"] if isinstance(rows[0], dict) else rows[0][0])) if rows else 0

    last_prune = current_app.config.get("_LAST_RL_PRUNE_TS", 0.0)
    now = time.time()
    if now - last_prune > 600:
        current_app.config["_LAST_RL_PRUNE_TS"] = now
        try:
            db_execute("DELETE FROM rate_limit_events WHERE created_at < NOW() - INTERVAL '2 days'")
        except Exception:
            pass

    return c > limit


def init_db() -> None:
    schema_init = current_app.config.get("INIT_DB_FUNC")
    if callable(schema_init):
        schema_init()


def _twilio_auth_token() -> str:
    return (os.environ.get("TWILIO_AUTH_TOKEN") or "").strip()


def _twilio_inbound_enabled() -> bool:
    return (os.environ.get("TWILIO_INBOUND_ENABLED", "false").strip().lower() == "true")


def _twilio_status_enabled() -> bool:
    return (os.environ.get("TWILIO_STATUS_ENABLED", "false").strip().lower() == "true")


def _validate_twilio_request() -> None:
    if RequestValidator is None:
        abort(500)

    sig = request.headers.get("X-Twilio-Signature", "")
    if not sig:
        abort(403)

    url = request.url
    xf_proto = (request.headers.get("X-Forwarded-Proto") or "").lower()
    if xf_proto == "https" and url.startswith("http://"):
        url = "https://" + url[len("http://"):]

    validator = RequestValidator(_twilio_auth_token())
    form = request.form.to_dict(flat=True)

    if not validator.validate(url, form, sig):
        abort(403)


def _normalize_last10(s: str) -> str:
    d = "".join(ch for ch in (s or "") if ch.isdigit())
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    if len(d) > 10:
        d = d[-10:]
    return d


@twilio.route("/twilio/inbound", methods=["POST"])
def twilio_inbound():
    """
    Twilio posts inbound messages here.
    We record STOP type words as opt out in our DB, and we reply using TwiML.
    """

    if not _twilio_inbound_enabled():
        return current_app.response_class("", mimetype="text/xml")

    ip = _client_ip()
    if _rate_limited(f"twilio_inbound_ip:{ip}", 60, 60):
        return current_app.response_class("", mimetype="text/xml")

    msg_sid = (request.form.get("MessageSid") or "").strip()
    if msg_sid and _rate_limited(f"twilio_msgsid:{msg_sid}", 1, 86400):
        return current_app.response_class("", mimetype="text/xml")

    _validate_twilio_request()

    init_db()

    from_number = (request.form.get("From") or "").strip()
    body = (request.form.get("Body") or "").strip().lower()

    stop_words = {"stop", "unsubscribe", "cancel", "end", "quit"}
    start_words = {"start", "yes", "unstop", "subscribe"}
    help_words = {"help", "info"}

    if body not in stop_words and body not in start_words and body not in help_words:
        return current_app.response_class("", mimetype="text/xml")

    kind = g.get("db_kind")
    sender10 = _normalize_last10(from_number)

    if sender10 and _rate_limited(f"twilio_inbound_from:{sender10}", 10, 60):
        return current_app.response_class("", mimetype="text/xml")

    reply_text = ""

    if body in stop_words:
        try:
            rows = db_fetchall(
                """
                SELECT id, shelter, phone
                FROM residents
                WHERE phone IS NOT NULL AND phone != ''
                ORDER BY id DESC
                LIMIT 300
                """
            )
        except Exception:
            rows = []

        for r in rows or []:
            r_id = r["id"] if isinstance(r, dict) else r[0]
            r_shelter = r["shelter"] if isinstance(r, dict) else r[1]
            r_phone = r["phone"] if isinstance(r, dict) else r[2]

            if _normalize_last10(str(r_phone or "")) != sender10:
                continue

            db_execute(
                """
                UPDATE residents
                SET sms_opt_in = %s,
                    sms_opt_out_at = %s,
                    sms_opt_out_source = %s
                WHERE id = %s AND shelter = %s
                """
                if kind == "pg"
                else """
                UPDATE residents
                SET sms_opt_in = ?,
                    sms_opt_out_at = ?,
                    sms_opt_out_source = ?
                WHERE id = ? AND shelter = ?
                """,
                (0, utcnow_iso(), "twilio_inbound", r_id, r_shelter),
            )

        reply_text = "You are unsubscribed from Downtown Women's Center Alerts. No more messages will be sent. Reply START to rejoin."

    elif body in help_words or body in start_words:
        return current_app.response_class("", mimetype="text/xml")

    else:
        reply_text = "For help contact staff."

    twiml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Response>"
        f"<Message>{reply_text}</Message>"
        "</Response>"
    )
    return current_app.response_class(twiml, mimetype="text/xml")


@twilio.route("/twilio/status", methods=["POST"])
def twilio_status():
    if not _twilio_status_enabled():
        return "OK", 200

    ip = _client_ip()
    if _rate_limited(f"twilio_status_ip:{ip}", 120, 60):
        return "OK", 200

    _validate_twilio_request()

    message_sid = (request.form.get("MessageSid") or "").strip()
    message_status = (request.form.get("MessageStatus") or "").strip()

    if message_sid and message_status:
        if _rate_limited(f"twilio_status:{message_sid}:{message_status}", 1, 172800):
            return "OK", 200

    init_db()
    kind = g.get("db_kind")

    error_code = (request.form.get("ErrorCode") or "").strip()
    to_number = (request.form.get("To") or "").strip()
    from_number = (request.form.get("From") or "").strip()
    account_sid = (request.form.get("AccountSid") or "").strip()
    api_version = (request.form.get("ApiVersion") or "").strip()
    created_at = utcnow_iso()

    if message_sid and message_status:
        db_execute(
            """
            INSERT INTO twilio_message_status
              (message_sid, message_status, error_code, to_number, from_number, account_sid, api_version, created_at)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            if kind == "pg"
            else """
            INSERT INTO twilio_message_status
              (message_sid, message_status, error_code, to_number, from_number, account_sid, api_version, created_at)
            VALUES
              (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_sid,
                message_status,
                (error_code or None),
                (to_number or None),
                (from_number or None),
                (account_sid or None),
                (api_version or None),
                created_at,
            ),
        )

    return "OK", 200
