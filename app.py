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
from db import schema
from core.auth import require_login
from core.auth import require_shelter
from core.helpers import is_postgres, db_placeholder, utcnow_iso, fmt_date, fmt_dt, fmt_time_only, fmt_pretty_date
from core.helpers import safe_url_for
from core.db import get_db, close_db, db_execute, db_fetchone, db_fetchall
from core.audit import log_action
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Optional

from flask import Flask, Response, current_app, g, redirect, render_template, request, session, url_for, flash, abort

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from zoneinfo import ZoneInfo


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

# User roles
USER_ROLES = {"admin", "staff", "case_manager", "ra"}

ROLE_LABELS = {
    "admin": "Admin",
    "staff": "Staff",
    "ra": "RA DESK",
    "case_manager": "Case Mgr",
}

# Any role allowed to use normal staff pages
STAFF_ROLES = {"admin", "staff", "case_manager", "ra"}

# Only these roles can perform permanent transfers
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
    # Use remote_addr (already normalized by ProxyFix) to avoid
    # trusting raw X-Forwarded-For header content directly.
    return (request.remote_addr or "").strip() or "unknown"
    
# Lightweight in process cleanup throttle for rate_limit_events pruning
_LAST_RL_PRUNE_TS = 0.0

# Fallback limiter used only when not on Postgres (sqlite or other)
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

    Behavior: allows up to `limit` events in `window_seconds`.
    The (limit+1)th attempt within the window will be blocked.
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


# CSRF token generator for templates
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

@app.route("/_routes")
def list_routes():
    import html

    out = []
    for r in app.url_map.iter_rules():
        out.append(f"{html.escape(r.endpoint)} -&gt; {html.escape(str(r.rule))}")
    return "<br>".join(sorted(out))

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
            leave_items.append({
                "status": status.capitalize(),
                "leave_at": fmt_dt(leave_at),
                "return_at": fmt_dt(return_at),
            })

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
            transport_items.append({
                "status": status.capitalize(),
                "needed_at": fmt_dt(needed_at),
                "driver_name": driver_name,
            })

    return {
        "leave_items": leave_items,
        "transport_items": transport_items,
    }
    
    
def parse_dt(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)

def send_sms(to_number: str, message: str) -> None:

    # GLOBAL SMS PANIC SWITCH
    if os.environ.get("SMS_SYSTEM_ENABLED", "true").lower() != "true":
        return

    if not TWILIO_ENABLED:
        return

    # COMPLIANCE GATE: never send unless allowed by our consent + opt out records
    try:
        if not sms_is_allowed_for_number(to_number):
            return
    except Exception:
        # If anything goes wrong checking consent, fail closed (do not send)
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
        
    # OUTBOUND CIRCUIT BREAKER
    # Caps sends even if app logic accidentally loops.
    try:
        per_number_per_hour = int(os.environ.get("SMS_OUTBOUND_PER_NUMBER_PER_HOUR", "6"))
    except Exception:
        per_number_per_hour = 6

    try:
        global_per_minute = int(os.environ.get("SMS_OUTBOUND_GLOBAL_PER_MIN", "30"))
    except Exception:
        global_per_minute = 30

    to10 = _normalize_us_phone_10(to_e164) or to_e164

    # Global cap (all outbound)
    if _rate_limited("sms_out_global", global_per_minute, 60):
        return

    # Per number cap
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

# Postgres connection pool

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


def ensure_admin_bootstrap() -> None:
    row = db_fetchone("SELECT COUNT(1) AS c FROM staff_users WHERE role = 'admin'")
    count = int(row["c"] if isinstance(row, dict) else row[0])
    if count > 0:
        return

    admin_user = (os.environ.get("ADMIN_USERNAME") or "").strip()
    admin_pass = (os.environ.get("ADMIN_PASSWORD") or "").strip()
    if not admin_user or not admin_pass:
        return

    db_execute(
        "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (%s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
        (admin_user, generate_password_hash(admin_pass), "admin", True, utcnow_iso()),
    )

 # DATABASE SCHEMA INITIALIZATION (moving to db/schema.py later)       
def legacy_init_db() -> None:
    get_db()
    kind = g.get("db_kind")

    # SMS consent fields for compliance
    if kind == "pg":
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in BOOLEAN NOT NULL DEFAULT FALSE")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in_source TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_out_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_out_source TEXT")
        except Exception:
            pass
    else:
        # SQLite does not support IF NOT EXISTS for ADD COLUMN
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in_source TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_out_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_out_source TEXT")
        except Exception:
            pass

    def create(sqlite_sql: str, pg_sql: str) -> None:
        db_execute(pg_sql if kind == "pg" else sqlite_sql)

    create(
        """
        CREATE TABLE IF NOT EXISTS staff_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS staff_users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
    )

    create(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            public_name TEXT NOT NULL,
            primary_color TEXT,
            secondary_color TEXT,
            logo_url TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            public_name TEXT NOT NULL,
            primary_color TEXT,
            secondary_color TEXT,
            logo_url TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """,
    )
    
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

    try:
        if kind == "pg":
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS resident_code TEXT")
        else:
            db_execute("ALTER TABLE residents ADD COLUMN resident_code TEXT")
    except Exception:
        pass

    try:
        db_execute("CREATE UNIQUE INDEX IF NOT EXISTS residents_resident_code_uq ON residents (resident_code)")
    except Exception:
        pass

    # Seed first organization (safe if it already exists)
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

    create(
        """
        CREATE TABLE IF NOT EXISTS resident_transfers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          resident_id INTEGER NOT NULL,
          from_shelter TEXT NOT NULL,
          to_shelter TEXT NOT NULL,
          transferred_by TEXT NOT NULL,
          transferred_at TEXT NOT NULL,
          note TEXT,
          FOREIGN KEY(resident_id) REFERENCES residents(id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_transfers (
          id SERIAL PRIMARY KEY,
          resident_id INTEGER NOT NULL REFERENCES residents(id),
          from_shelter TEXT NOT NULL,
          to_shelter TEXT NOT NULL,
          transferred_by TEXT NOT NULL,
          transferred_at TIMESTAMP NOT NULL DEFAULT NOW(),
          note TEXT
        );
        """,
    )
    
    create(
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            resident_phone TEXT,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            leave_at TEXT NOT NULL,
            return_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by INTEGER,
            decision_note TEXT,
            check_in_at TEXT,
            check_in_by INTEGER
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            resident_phone TEXT,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            leave_at TEXT NOT NULL,
            return_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by INTEGER,
            decision_note TEXT,
            check_in_at TEXT,
            check_in_by INTEGER
        )
        """,
    )

    try:
        if kind == "pg":
            db_execute("ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS resident_phone TEXT")
        else:
            db_execute("ALTER TABLE leave_requests ADD COLUMN resident_phone TEXT")
    except Exception:
        pass

    create(
        """
        CREATE TABLE IF NOT EXISTS transport_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            needed_at TEXT NOT NULL,
            pickup_location TEXT NOT NULL,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            callback_phone TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            scheduled_at TEXT,
            scheduled_by INTEGER,
            driver_name TEXT,
            staff_notes TEXT,
            completed_at TEXT,
            completed_by INTEGER,
            cancelled_at TEXT,
            cancelled_by INTEGER,
            cancel_reason TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS transport_requests (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            needed_at TEXT NOT NULL,
            pickup_location TEXT NOT NULL,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            callback_phone TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            scheduled_at TEXT,
            scheduled_by INTEGER,
            driver_name TEXT,
            staff_notes TEXT,
            completed_at TEXT,
            completed_by INTEGER,
            cancelled_at TEXT,
            cancelled_by INTEGER,
            cancel_reason TEXT
        )
        """,
    )

    try:
        if g.get("db_kind") == "pg":
            db_execute("ALTER TABLE transport_requests DROP COLUMN IF EXISTS dob")
    except Exception:
        pass

    create(
        """
        CREATE TABLE IF NOT EXISTS attendance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,
            staff_user_id INTEGER,
            note TEXT,
            expected_back_time TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS attendance_events (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,
            staff_user_id INTEGER,
            note TEXT,
            expected_back_time TEXT
        )
        """,
    )

    create(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            shelter TEXT,
            staff_user_id INTEGER,
            action_type TEXT NOT NULL,
            action_details TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            shelter TEXT,
            staff_user_id INTEGER,
            action_type TEXT NOT NULL,
            action_details TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """,
    )
    
    create(
        """
        CREATE TABLE IF NOT EXISTS twilio_message_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_sid TEXT NOT NULL,
            message_status TEXT NOT NULL,
            error_code TEXT,
            to_number TEXT,
            from_number TEXT,
            account_sid TEXT,
            api_version TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS twilio_message_status (
            id SERIAL PRIMARY KEY,
            message_sid TEXT NOT NULL,
            message_status TEXT NOT NULL,
            error_code TEXT,
            to_number TEXT,
            from_number TEXT,
            account_sid TEXT,
            api_version TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """,
    )
    
    if kind == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS rate_limit_events (
              id SERIAL PRIMARY KEY,
              k TEXT NOT NULL,
              created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """
        )
        db_execute("CREATE INDEX IF NOT EXISTS rate_limit_events_k_idx ON rate_limit_events (k)")
        db_execute("CREATE INDEX IF NOT EXISTS rate_limit_events_created_at_idx ON rate_limit_events (created_at)")

    try:
        db_execute("CREATE INDEX IF NOT EXISTS twilio_message_status_sid_idx ON twilio_message_status (message_sid)")
    except Exception:
        pass

    try:
        db_execute("CREATE INDEX IF NOT EXISTS twilio_message_status_created_idx ON twilio_message_status (created_at)") 
    except Exception:
        pass
    
    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS leave_requests_shelter_status_return_idx "
            "ON leave_requests (shelter, status, return_at)"
        )
    except Exception:
        pass
    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS transport_requests_shelter_status_pickup_idx "
            "ON transport_requests (shelter, status, needed_at)"
        )
    except Exception:
        pass
    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS attendance_events_shelter_occurred_idx "
            "ON attendance_events (shelter, event_time)"
        )
    except Exception:
        pass
    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS residents_shelter_active_name_idx "
            "ON residents (shelter, is_active, last_name, first_name)"
        )
    except Exception:
        pass

    rows = db_fetchall(
        "SELECT id FROM residents WHERE resident_code IS NULL OR resident_code = ''"
        if kind == "pg"
        else "SELECT id FROM residents WHERE resident_code IS NULL OR resident_code = ''"
    )
    for r in rows:
        rid = r["id"] if isinstance(r, dict) else r[0]
        code = make_resident_code()
        for _ in range(10):
            exists = db_fetchone(
                "SELECT id FROM residents WHERE resident_code = %s"
                if kind == "pg"
                else "SELECT id FROM residents WHERE resident_code = ?",
                (code,),
            )
            if not exists:
                break
            code = make_resident_code()

        db_execute(
            "UPDATE residents SET resident_code = %s WHERE id = %s"
            if kind == "pg"
            else "UPDATE residents SET resident_code = ? WHERE id = ?",
            (code, rid),
        )

    ensure_admin_bootstrap()

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


# ============================
# Routes
# ============================



@app.get("/privacy")
def privacy_policy():
    return render_template("privacy.html")

@app.get("/terms")
def terms_and_conditions():
    return render_template("terms.html")


@app.route("/")
def public_home():
    return redirect(url_for("resident_requests.resident_leave"))
    

@app.route("/twilio/inbound", methods=["POST"])
def twilio_inbound():
    """
    Twilio posts inbound messages here.
    We record STOP type words as opt out in our DB, and we reply using TwiML.
    """

    if not TWILIO_INBOUND_ENABLED:
        return app.response_class("", mimetype="text/xml")

    ip = _client_ip()
    if _rate_limited(f"twilio_inbound_ip:{ip}", 60, 60):
        return app.response_class("", mimetype="text/xml")

    msg_sid = (request.form.get("MessageSid") or "").strip()
    if msg_sid and _rate_limited(f"twilio_msgsid:{msg_sid}", 1, 86400):
        return app.response_class("", mimetype="text/xml")

    # Require validator when inbound is enabled
    if RequestValidator is None:
        abort(500)

    sig = request.headers.get("X-Twilio-Signature", "")
    if not sig:
        abort(403)

    # Build the URL used for validation (account for proxy https)
    url = request.url
    xf_proto = (request.headers.get("X-Forwarded-Proto") or "").lower()
    if xf_proto == "https" and url.startswith("http://"):
        url = "https://" + url[len("http://"):]

    validator = RequestValidator(TWILIO_AUTH_TOKEN or "")
    form = request.form.to_dict(flat=True)

    if not validator.validate(url, form, sig):
        abort(403)
    
    init_db()

    from_number = (request.form.get("From") or "").strip()
    body = (request.form.get("Body") or "").strip().lower()
    
    stop_words = {"stop", "unsubscribe", "cancel", "end", "quit"}
    start_words = {"start", "yes", "unstop", "subscribe"}
    help_words = {"help", "info"}
    
    if body not in stop_words and body not in start_words and body not in help_words:
        return app.response_class("", mimetype="text/xml")
        
    kind = g.get("db_kind")

    def normalize_last10(s: str) -> str:
        d = "".join(ch for ch in (s or "") if ch.isdigit())
        if len(d) == 11 and d.startswith("1"):
            d = d[1:]
        if len(d) > 10:
            d = d[-10:]
        return d

    sender10 = normalize_last10(from_number)

    if sender10 and _rate_limited(f"twilio_inbound_from:{sender10}", 10, 60):
        return app.response_class("", mimetype="text/xml")

    

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

            if normalize_last10(str(r_phone or "")) != sender10:
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
        return app.response_class("", mimetype="text/xml")

    else:
        reply_text = "For help contact staff."

    twiml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Response>"
        f"<Message>{reply_text}</Message>"
        "</Response>"
    )
    return app.response_class(twiml, mimetype="text/xml")

@app.route("/twilio/status", methods=["POST"])
def twilio_status():
    if not TWILIO_STATUS_ENABLED:
        return "OK", 200

    ip = _client_ip()
    if _rate_limited(f"twilio_status_ip:{ip}", 120, 60):
        return "OK", 200

    # Require validator when status callbacks are enabled
    if RequestValidator is None:
        abort(500)

    sig = request.headers.get("X-Twilio-Signature", "")
    if not sig:
        abort(403)

    # Build the URL used for validation (account for proxy https)
    url = request.url
    xf_proto = (request.headers.get("X-Forwarded-Proto") or "").lower()
    if xf_proto == "https" and url.startswith("http://"):
        url = "https://" + url[len("http://"):]

    validator = RequestValidator(TWILIO_AUTH_TOKEN or "")
    form = request.form.to_dict(flat=True)

    if not validator.validate(url, form, sig):
        abort(403)

    message_sid = (request.form.get("MessageSid") or "").strip()
    message_status = (request.form.get("MessageStatus") or "").strip()

    # Idempotency: store each status transition once
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


# ---- Dangerous Admin Maintenance ----

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.after_request
def add_cache_headers(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
     # Baseline security headers
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")

    # Limit framing via CSP as modern defense-in-depth.
    # Keep policy conservative and compatible with existing templates.
    csp = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    response.headers.setdefault("Content-Security-Policy", csp)

    # Enable HSTS only when running behind HTTPS in production.
    # Prevents local HTTP development from being forced to HTTPS.
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    
    return response

if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="127.0.0.1", port=5000)
















