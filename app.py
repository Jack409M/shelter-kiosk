from __future__ import annotations

import importlib
import pkgutil
import os
import io
import csv
import sqlite3
import secrets
import time
import logging

from collections import deque
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Optional
from zoneinfo import ZoneInfo

from flask import Flask, Response, current_app, g, redirect, render_template, request, session, url_for, flash, abort
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

from db import schema
from core.auth import require_login
from core.auth import require_shelter
from core.helpers import is_postgres, db_placeholder, utcnow_iso, fmt_date, fmt_dt, fmt_time_only, fmt_pretty_date
from core.helpers import safe_url_for
from core.db import get_db, close_db, db_execute, db_fetchone, db_fetchall
from core.audit import log_action
from core.sms import sms_is_allowed_for_number


try:
    from twilio.rest import Client
    from twilio.request_validator import RequestValidator
except Exception:
    Client = None
    RequestValidator = None


TWILIO_ENABLED = os.environ.get("TWILIO_ENABLED", "false").lower() == "true"
TWILIO_INBOUND_ENABLED = os.environ.get("TWILIO_INBOUND_ENABLED", "false").strip().lower() == "true"
TWILIO_STATUS_ENABLED = os.environ.get("TWILIO_STATUS_ENABLED", "false").strip().lower() == "true"
TWILIO_STATUS_CALLBACK_URL = (os.environ.get("TWILIO_STATUS_CALLBACK_URL") or "").strip()

SHELTERS = ["Abba", "Haven", "Gratitude"]
MAX_LEAVE_DAYS = 7
MIN_STAFF_PASSWORD_LEN = 8

USER_ROLES = {"admin", "staff", "case_manager", "ra"}

ROLE_LABELS = {
    "admin": "Admin",
    "staff": "Staff",
    "ra": "RA DESK",
    "case_manager": "Case Mgr",
}

STAFF_ROLES = {"admin", "staff", "case_manager", "ra"}
TRANSFER_ROLES = {"admin", "case_manager"}

APP_DIR = os.path.abspath(os.path.dirname(__file__))
SQLITE_PATH = os.path.join(APP_DIR, "shelter_operations.db")

DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
ENABLE_DEBUG_ROUTES = (os.environ.get("ENABLE_DEBUG_ROUTES") or "").strip().lower() in {"1", "true", "yes", "on"}
KIOSK_PIN = (os.environ.get("KIOSK_PIN") or "").strip()
ENABLE_DANGEROUS_ADMIN_ROUTES = (os.environ.get("ENABLE_DANGEROUS_ADMIN_ROUTES") or "").strip().lower() in {"1", "true", "yes", "on"}
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")

app = Flask(__name__)
app.jinja_env.globals["safe_url_for"] = safe_url_for
app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL")
app.config["SQLITE_PATH"] = os.environ.get("SQLITE_PATH", SQLITE_PATH)
app.teardown_appcontext(close_db)
app.logger.setLevel(logging.DEBUG)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)


def register_blueprints(app: Flask) -> None:
    import routes
    from flask import Blueprint

    for _, module_name, _ in pkgutil.iter_modules(routes.__path__):
        module = importlib.import_module(f"routes.{module_name}")

        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, Blueprint) and obj.name not in app.blueprints:
                app.register_blueprint(obj)


register_blueprints(app)


@app.before_request
def log_request_info():
    try:
        app.logger.debug(
            f"REQUEST method={request.method} path={request.path} endpoint={request.endpoint}"
        )
        app.logger.debug(f"URL RULE {request.url_rule}")

        if request.method == "POST":
            app.logger.debug(f"FORM KEYS {list(request.form.keys())}")

    except Exception as e:
        app.logger.debug(f"LOGGING ERROR {e}")


secret = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
if not secret:
    raise RuntimeError("FLASK_SECRET_KEY is required and must be set in the environment.")
app.secret_key = secret

app.permanent_session_lifetime = timedelta(hours=8)
COOKIE_SECURE = (os.environ.get("COOKIE_SECURE") or "").strip().lower() in {"1", "true", "yes", "on"}

app.config.update(
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


def _client_ip() -> str:
    """
    Use ProxyFix normalized remote_addr rather than trusting raw forwarded headers.
    """
    return (request.remote_addr or "").strip() or "unknown"


# In process cleanup throttle for Postgres rate_limit_events pruning.
_LAST_RL_PRUNE_TS = 0.0

# Fallback limiter used only when not on Postgres.
_RATE_BUCKETS_MEM: dict[str, deque[float]] = {}


def _rate_limited_memory(key: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    bucket = _RATE_BUCKETS_MEM.get(key)
    if bucket is None:
        bucket = deque()
        _RATE_BUCKETS_MEM[key] = bucket

    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if len(bucket) >= limit:
        return True

    bucket.append(now)
    return False


def _rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    """
    Postgres backed rate limiter.

    Returns True when the caller should be blocked.
    Allows up to `limit` events in `window_seconds`.
    The next attempt inside the same window is blocked.
    """
    if g.get("db_kind") != "pg":
        return _rate_limited_memory(key, limit, window_seconds)

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
    c = int(row["c"] if isinstance(row, dict) else row[0])

    global _LAST_RL_PRUNE_TS
    now = time.time()
    if now - _LAST_RL_PRUNE_TS > 600:
        _LAST_RL_PRUNE_TS = now
        try:
            db_execute("DELETE FROM rate_limit_events WHERE created_at < NOW() - INTERVAL '2 days'")
        except Exception:
            pass

    return c > limit


def _csrf_token() -> str:
    tok = session.get("_csrf_token")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf_token"] = tok
    return tok


app.jinja_env.globals["csrf_token"] = _csrf_token


def _csrf_protect():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None

    exempt_endpoints = {
        "resident_requests.sms_consent",
        "twilio.twilio_inbound",
        "twilio.twilio_status",
    }

    if request.endpoint in exempt_endpoints:
        return None

    sent = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get("_csrf_token") or ""

    if not sent or not expected or sent != expected:
        flash("Session expired. Please retry.", "error")

        fallback = url_for("auth.staff_login")
        if request.endpoint and (
            str(request.endpoint).startswith("resident_")
            or str(request.endpoint).startswith("resident_requests.")
        ):
            fallback = url_for("resident_requests.resident_signin")

        return redirect(request.referrer or fallback)

    return None


@app.before_request
def _csrf_before_request():
    resp = _csrf_protect()
    if resp is not None:
        return resp


@app.context_processor
def inject_shelters():
    return {
        "all_shelters": SHELTERS,
        "current_shelter": session.get("shelter"),
    }


@app.context_processor
def inject_resident_dashboard_status():
    if (request.endpoint or "") != "resident_portal.home":
        return {}

    if "resident_id" not in session:
        return {}

    init_db()

    resident_identifier = (session.get("resident_identifier") or "").strip()
    if not resident_identifier:
        return {}

    all_leave_rows = db_fetchall(
        """
        SELECT status, shelter, resident_identifier, leave_at, return_at
        FROM leave_requests
        WHERE resident_identifier = %s
        ORDER BY leave_at ASC
        """
        if is_postgres()
        else """
        SELECT status, shelter, resident_identifier, leave_at, return_at
        FROM leave_requests
        WHERE resident_identifier = ?
        ORDER BY leave_at ASC
        """,
        (resident_identifier,),
    )

    all_transport_rows = db_fetchall(
        """
        SELECT status, shelter, resident_identifier, needed_at, driver_name
        FROM transport_requests
        WHERE resident_identifier = %s
        ORDER BY needed_at ASC
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT status, shelter, resident_identifier, needed_at, driver_name
        FROM transport_requests
        WHERE resident_identifier = ?
        ORDER BY needed_at ASC
        """,
        (resident_identifier,),
    )

    leave_items = []
    for row in all_leave_rows:
        if isinstance(row, dict):
            status = (row.get("status") or "").lower()
            leave_at = row.get("leave_at")
            return_at = row.get("return_at")
        else:
            status = (row[0] or "").lower()
            leave_at = row[3]
            return_at = row[4]

        if status in ["pending", "approved"]:
            leave_items.append(
                {
                    "status": status.capitalize(),
                    "leave_at": fmt_dt(leave_at),
                    "return_at": fmt_dt(return_at),
                }
            )

    transport_items = []
    for row in all_transport_rows:
        if isinstance(row, dict):
            status = (row.get("status") or "").lower()
            needed_at = row.get("needed_at")
            driver_name = row.get("driver_name") or ""
        else:
            status = (row[0] or "").lower()
            needed_at = row[3]
            driver_name = row[4] or ""

        if status in ["pending", "scheduled"]:
            transport_items.append(
                {
                    "status": status.capitalize(),
                    "needed_at": fmt_dt(needed_at),
                    "driver_name": driver_name,
                }
            )

    return {
        "leave_items": leave_items,
        "transport_items": transport_items,
    }


def parse_dt(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


def send_sms(to_number: str, message: str) -> None:
    """
    Outbound SMS sender with:
    global panic switch,
    Twilio enable gate,
    consent enforcement,
    per number and global rate limiting.
    """

    if os.environ.get("SMS_SYSTEM_ENABLED", "true").lower() != "true":
        return

    if not TWILIO_ENABLED:
        return

    try:
        if not sms_is_allowed_for_number(to_number):
            return
    except Exception:
        return

    if not Client:
        return

    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
        return

    raw = (to_number or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())

    if raw.startswith("+"):
        to_e164 = raw
    elif len(digits) == 10:
        to_e164 = "+1" + digits
    elif len(digits) == 11 and digits.startswith("1"):
        to_e164 = "+" + digits
    else:
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


def make_resident_code(length: int = 8) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_resident_code() -> str:
    code = make_resident_code(8)

    for _ in range(15):
        exists = db_fetchone(
            "SELECT id FROM residents WHERE resident_code = %s"
            if g.get("db_kind") == "pg"
            else "SELECT id FROM residents WHERE resident_code = ?",
            (code,),
        )
        if not exists:
            return code
        code = make_resident_code(8)

    return code


def generate_resident_identifier() -> str:
    return secrets.token_urlsafe(12)


def resident_session_start(resident_row: Any, shelter: str, resident_code: str) -> None:
    session.permanent = True

    session["resident_id"] = resident_row["id"] if isinstance(resident_row, dict) else resident_row[0]
    session["resident_identifier"] = (
        resident_row["resident_identifier"] if isinstance(resident_row, dict) else resident_row[2]
    )
    session["resident_first"] = (
        resident_row["first_name"] if isinstance(resident_row, dict) else resident_row[4]
    )
    session["resident_last"] = (
        resident_row["last_name"] if isinstance(resident_row, dict) else resident_row[5]
    )
    session["resident_phone"] = (
        (resident_row["phone"] if isinstance(resident_row, dict) else resident_row[6]) or ""
    )
    session["resident_shelter"] = shelter
    session["resident_code"] = resident_code


def record_resident_transfer(resident_id: int, from_shelter: str, to_shelter: str, note: str = ""):
    actor = session.get("username") or "unknown"

    if app.config.get("DATABASE_URL"):
        db_execute(
            """
            INSERT INTO resident_transfers
              (resident_id, from_shelter, to_shelter, transferred_by, note)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (resident_id, from_shelter, to_shelter, actor, note or None),
        )
    else:
        db_execute(
            """
            INSERT INTO resident_transfers
              (resident_id, from_shelter, to_shelter, transferred_by, transferred_at, note)
            VALUES (?, ?, ?, ?, datetime('now'), ?)
            """,
            (resident_id, from_shelter, to_shelter, actor, note or None),
        )

    staff_id = session.get("staff_user_id")
    log_action(
        "resident",
        resident_id,
        from_shelter,
        staff_id,
        "resident_transfer",
        f"from={from_shelter} to={to_shelter} note={note}".strip(),
    )


# Database schema initialization.
# Current state:
# schema mutations and indexes are mostly delegated to db/schema.py.
# Future extraction targets:
#   1. move inline table create blocks below into db/schema.py one table at a time
#   2. replace local create(...) usage with schema owned helpers
#   3. eventually collapse this function into schema.init_db()
def legacy_init_db() -> None:
    get_db()
    kind = g.get("db_kind")

    schema.ensure_sms_consent_columns(kind)

    def create(sqlite_sql: str, pg_sql: str) -> None:
        schema._create(sqlite_sql, pg_sql, kind)

    # Already extracted to db/schema.py
    schema.ensure_staff_users_table(kind)
    schema.ensure_organizations_table(kind)
    

    # Future extraction target: residents table
    create(
        """
        CREATE TABLE IF NOT EXISTS residents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            resident_code TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS residents (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            resident_code TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
    )

    schema.ensure_resident_code_schema(kind)

    # Seed first organization.
    # Left inline for now because it is data bootstrap rather than schema definition.
    try:
        db_execute(
            """
            INSERT INTO organizations
            (name, slug, public_name, primary_color, secondary_color, created_at)
            VALUES
            ('Downtown Womens Center', 'dwc', 'Downtown Womens Center', '#4f8fbe', '#3f79a5', ?)
            """,
            (datetime.utcnow().isoformat(),),
        )
    except Exception:
        pass
    # Already extracted to db/schema.py
    schema.ensure_resident_transfers_table(kind)
    schema.ensure_transport_requests_table(kind)
    schema.drop_transport_dob_column_if_present(kind)
    schema.ensure_attendance_events_table(kind)
    schema.ensure_audit_log_table(kind)
    schema.ensure_twilio_message_status_table(kind)

    if kind == "pg":
        schema.ensure_rate_limit_events_table(kind)
        schema.ensure_rate_limit_event_indexes(kind)

    schema.ensure_twilio_message_status_indexes()
    schema.ensure_common_app_indexes()
    schema.backfill_resident_codes(kind, make_resident_code)
    schema.ensure_admin_bootstrap()


init_db = legacy_init_db
app.config["INIT_DB_FUNC"] = init_db


def require_staff_or_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in STAFF_ROLES:
            flash("Staff only.", "error")
            return redirect(url_for("auth.staff_home"))
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin only.", "error")
            return redirect(url_for("auth.staff_home"))
        return fn(*args, **kwargs)

    return wrapper


def require_resident(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "resident_id" not in session:
            return redirect(url_for("resident_requests.resident_signin", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


def require_transfer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in TRANSFER_ROLES:
            flash("Admin or case manager only.", "error")
            return redirect(url_for("auth.staff_home"))
        return fn(*args, **kwargs)

    return wrapper


def require_resident_create(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in {"admin", "case_manager"}:
            flash("Admin or case manager only.", "error")
            return redirect(url_for("residents.staff_residents"))
        return fn(*args, **kwargs)

    return wrapper


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.after_request
def add_cache_headers(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400"

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")

    csp = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers.setdefault("Content-Security-Policy", csp)

    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    return response


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="127.0.0.1", port=5000)








