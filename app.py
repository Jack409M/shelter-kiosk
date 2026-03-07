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
        "sms_consent",
         "twilio_inbound",
         "twilio_status",
    }

    if request.endpoint in exempt_endpoints:
        return None

    sent = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get("_csrf_token") or ""

    if not sent or not expected or sent != expected:
        flash("Session expired. Please retry.", "error")

        fallback = url_for("staff_login")
        if request.endpoint and str(request.endpoint).startswith("resident_"):
            fallback = url_for("resident_signin")

        return redirect(request.referrer or fallback)

    return None


@app.before_request
def _csrf_before_request():
    resp = _csrf_protect()
    if resp is not None:
        return resp

@app.route("/_routes")
def list_routes():
    out = []
    for r in app.url_map.iter_rules():
        out.append(f"{r.endpoint} -> {r.rule}")
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
    
    leave_row = db_fetchone(
        """
        SELECT status, leave_at, return_at, decision_note, submitted_at
        FROM leave_requests
        WHERE shelter = %s AND resident_identifier = %s
        ORDER BY submitted_at DESC
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT status, leave_at, return_at, decision_note, submitted_at
        FROM leave_requests
        WHERE shelter = ? AND resident_identifier = ?
        ORDER BY submitted_at DESC
        LIMIT 1
        """,
        (shelter, resident_identifier),
    )

    transport_row = db_fetchone(
        """
        SELECT status, needed_at, driver_name, staff_notes, submitted_at
        FROM transport_requests
        WHERE shelter = %s AND resident_identifier = %s
        ORDER BY submitted_at DESC
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT status, needed_at, driver_name, staff_notes, submitted_at
        FROM transport_requests
        WHERE shelter = ? AND resident_identifier = ?
        ORDER BY submitted_at DESC
        LIMIT 1
        """,
        (shelter, resident_identifier),
    )

    leave_status_text = "You do not currently have a leave request."
    leave_status_note = ""

    if leave_row:
        leave_status = (leave_row["status"] if isinstance(leave_row, dict) else leave_row[0]) or ""
        leave_at = leave_row["leave_at"] if isinstance(leave_row, dict) else leave_row[1]
        return_at = leave_row["return_at"] if isinstance(leave_row, dict) else leave_row[2]
        decision_note = (leave_row["decision_note"] if isinstance(leave_row, dict) else leave_row[3]) or ""

        if leave_status == "pending":
            leave_status_text = "Your leave request is pending staff review."
        elif leave_status == "approved":
            leave_status_text = f"Approved from {fmt_date(leave_at)} through {fmt_dt(return_at)}."
        elif leave_status == "denied":
            leave_status_text = "Your most recent leave request was denied."
            if decision_note:
                leave_status_note = decision_note
        elif leave_status == "checked_in":
            leave_status_text = "Your most recent leave request has been checked in."
        else:
            leave_status_text = f"Current leave status: {leave_status.title()}."

    transport_status_text = "No transportation is currently scheduled."
    transport_status_note = ""

    if transport_row:
        transport_status = (transport_row["status"] if isinstance(transport_row, dict) else transport_row[0]) or ""
        needed_at = transport_row["needed_at"] if isinstance(transport_row, dict) else transport_row[1]
        driver_name = (transport_row["driver_name"] if isinstance(transport_row, dict) else transport_row[2]) or ""
        staff_notes = (transport_row["staff_notes"] if isinstance(transport_row, dict) else transport_row[3]) or ""

        if transport_status == "pending":
            transport_status_text = "Your transportation request is pending staff review."
        elif transport_status == "scheduled":
            transport_status_text = f"Transportation is scheduled for {fmt_dt(needed_at)}."
            if driver_name:
                transport_status_note = f"Driver: {driver_name}"
        elif transport_status == "completed":
            transport_status_text = "Your most recent transportation request was completed."
        elif transport_status == "cancelled":
            transport_status_text = "Your most recent transportation request was cancelled."
            if staff_notes:
                transport_status_note = staff_notes
        else:
            transport_status_text = f"Current transportation status: {transport_status.title()}."

    return {
        "leave_status_text": leave_status_text,
        "leave_status_note": leave_status_note,
        "transport_status_text": transport_status_text,
        "transport_status_note": transport_status_note,
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

def require_staff_or_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in STAFF_ROLES:
            flash("Staff only.", "error")
            return redirect(url_for("staff_home"))
        return fn(*args, **kwargs)

    return wrapper

def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin only.", "error")
            return redirect(url_for("staff_home"))
        return fn(*args, **kwargs)

    return wrapper


def require_resident(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "resident_id" not in session:
            return redirect(url_for("resident_signin", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


def require_transfer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in TRANSFER_ROLES:
            flash("Admin or case manager only.", "error")
            return redirect(url_for("staff_home"))
        return fn(*args, **kwargs)

    return wrapper


def require_resident_create(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in {"admin", "case_manager"}:
            flash("Admin or case manager only.", "error")
            return redirect(url_for("staff_residents"))
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
    return redirect(url_for("resident_leave"))


@app.post("/debug/csrf-post")
@require_login
def debug_csrf_post():
    if not ENABLE_DEBUG_ROUTES:
        abort(404)
    return "CSRF OK", 200


@app.route("/debug/db")
@require_login
@require_admin
def debug_db():
    if not ENABLE_DEBUG_ROUTES:
        abort(404)

    try:
        init_db()
    except Exception:
        return {"ok": False, "error": "db init failed", "db_kind": g.get("db_kind")}, 500

    return {"ok": True, "db_kind": g.get("db_kind")}



@app.route("/resident", methods=["GET", "POST"])
def resident_signin():
    init_db()

    next_url = (request.args.get("next") or request.form.get("next") or "").strip()

    if request.method == "GET":
        return render_template("resident_signin.html")

    resident_code = (request.form.get("resident_code") or "").strip()

    row = db_fetchone(
        "SELECT * FROM residents WHERE resident_code = %s"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM residents WHERE resident_code = ?",
        (resident_code,),
    )

    if not row:
        flash("Invalid Resident Code.", "error")
        return render_template("resident_signin.html"), 401

    shelter = (row.get("shelter") or "").strip()
    resident_session_start(row, shelter, resident_code)

    allowed_next = {
        url_for("resident_leave"),
        url_for("resident_transport"),
        url_for("resident_portal.home"),
    }

    if next_url not in allowed_next:
        next_url = url_for("resident_portal.home")

    if not session.get("sms_consent_done"):
        return redirect(url_for("resident_consent", next=next_url))

    return redirect(next_url)

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


@app.get("/resident/logout")
def resident_logout():
    for k in [
        "resident_id",
        "resident_identifier",
        "resident_first",
        "resident_last",
        "resident_phone",
        "resident_shelter",
        "resident_code",
        "sms_consent_done",
        "sms_opt_in",
    ]:
        session.pop(k, None)
    return redirect(url_for("resident_signin"))

@app.route("/leave", methods=["GET", "POST"])
@require_resident
def resident_leave():
    init_db()

    if request.method == "GET":
        shelter = session.get("resident_shelter") or ""
        return render_template("resident_leave.html", shelter=shelter, max_days=MAX_LEAVE_DAYS)

    shelter = session.get("resident_shelter") or ""
    resident_identifier = session.get("resident_identifier") or ""
    first = session.get("resident_first") or ""
    last = session.get("resident_last") or ""

    resident_phone = (request.form.get("resident_phone") or "").strip()
    if resident_phone:
        db_execute(
            "UPDATE residents SET phone = %s WHERE shelter = %s AND resident_identifier = %s"
            if g.get("db_kind") == "pg"
            else "UPDATE residents SET phone = ? WHERE shelter = ? AND resident_identifier = ?",
            (resident_phone, shelter, resident_identifier),
        )
        session["resident_phone"] = resident_phone

    destination = (request.form.get("destination") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    resident_notes = (request.form.get("resident_notes") or "").strip()
    leave_at_raw = (request.form.get("leave_at") or "").strip()
    return_at_raw = (request.form.get("return_at") or "").strip()
    agreed = request.form.get("agreed") == "on"

    errors: list[str] = []

    if not agreed:
        errors.append("You must accept the agreement.")

    if not first or not last or not destination or not leave_at_raw or not return_at_raw:
        errors.append("Complete all required fields.")

    # phone is optional, so no phone-required error

    try:
        leave_local_date = datetime.fromisoformat(leave_at_raw).date()
        return_local_date = datetime.fromisoformat(return_at_raw).date()

        if return_local_date < leave_local_date:
            errors.append("Return must be after leave.")

        if return_local_date > leave_local_date + timedelta(days=MAX_LEAVE_DAYS):
            errors.append(f"Maximum leave is {MAX_LEAVE_DAYS} days.")

        leave_local_dt = datetime.combine(leave_local_date, datetime.min.time()).replace(tzinfo=ZoneInfo("America/Chicago"))
        return_local_dt = datetime.combine(
            return_local_date,
            datetime.strptime("22:00", "%H:%M").time(),
        ).replace(tzinfo=ZoneInfo("America/Chicago"))

        leave_dt = leave_local_dt.astimezone(timezone.utc).replace(tzinfo=None)
        return_dt = return_local_dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        errors.append("Invalid date.")

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("resident_leave.html", shelters=SHELTERS, shelter=shelter, max_days=MAX_LEAVE_DAYS), 400

    sql = (
        """
        INSERT INTO leave_requests
        (shelter, resident_identifier, first_name, last_name, resident_phone, destination, reason, resident_notes, leave_at, return_at, status, submitted_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
        RETURNING id
        """
        if g.get("db_kind") == "pg"
        else """
        INSERT INTO leave_requests
        (shelter, resident_identifier, first_name, last_name, resident_phone, destination, reason, resident_notes, leave_at, return_at, status, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """
    )

    leave_iso = leave_dt.replace(microsecond=0).isoformat()
    return_iso = return_dt.replace(microsecond=0).isoformat()
    submitted = utcnow_iso()

    params = (
        shelter,
        resident_identifier or "",
        first,
        last,
        resident_phone,
        destination,
        reason or None,
        resident_notes or None,
        leave_iso,
        return_iso,
        submitted,
    )

    if g.get("db_kind") == "pg":
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql, params)
        req_id = cur.fetchone()[0]
        cur.close()
    else:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        req_id = cur.lastrowid

    log_action("leave", req_id, shelter, None, "create", "Resident submitted leave request")
    flash("Your leave request was submitted successfully.", "ok")
    return redirect(url_for("resident_portal.home"))

@app.route("/transport", methods=["GET", "POST"])
@require_resident
def resident_transport():
    init_db()

    if request.method == "GET":
        shelter = session.get("resident_shelter") or ""
        return render_template("resident_transport.html", shelter=shelter)

    shelter = session.get("resident_shelter") or ""
    resident_identifier = session.get("resident_identifier") or ""
    first = session.get("resident_first") or ""
    last = session.get("resident_last") or ""

    needed_raw = (request.form.get("needed_at") or "").strip()
    pickup = (request.form.get("pickup_location") or "").strip()
    destination = (request.form.get("destination") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    resident_notes = (request.form.get("resident_notes") or "").strip()
    callback_phone = (request.form.get("callback_phone") or "").strip()

    errors: list[str] = []
    if not first or not last or not needed_raw or not pickup or not destination:
        errors.append("Complete all required fields.")

    try:
        needed_local = parse_dt(needed_raw)
        needed_dt = (
            needed_local.replace(tzinfo=ZoneInfo("America/Chicago"))
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        if needed_dt < datetime.utcnow() - timedelta(minutes=1):
            errors.append("Needed time cannot be in the past.")
    except Exception:
        errors.append("Invalid needed date or time.")

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("resident_transport.html", shelter=shelter), 400

    sql = (
        """
        INSERT INTO transport_requests
        (shelter, resident_identifier, first_name, last_name, needed_at, pickup_location, destination, reason, resident_notes, callback_phone, status, submitted_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
        RETURNING id
        """
        if g.get("db_kind") == "pg"
        else """
        INSERT INTO transport_requests
        (shelter, resident_identifier, first_name, last_name, needed_at, pickup_location, destination, reason, resident_notes, callback_phone, status, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """
    )

    needed_iso = needed_dt.replace(microsecond=0).isoformat()
    submitted = utcnow_iso()

    params = (
        shelter,
        resident_identifier or "",
        first,
        last,
        needed_iso,
        pickup,
        destination,
        reason or None,
        resident_notes or None,
        callback_phone or None,
        submitted,
    )

    if g.get("db_kind") == "pg":
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql, params)
        req_id = cur.fetchone()[0]
        cur.close()
    else:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        req_id = cur.lastrowid

    log_action("transport", req_id, shelter, None, "create", "Resident submitted transport request")
    flash("Your transportation request was submitted successfully.", "ok")
    return redirect(url_for("resident_portal.home"))

@app.get("/sms-consent")
def sms_consent_public_alias():
    return redirect("/resident/sms-consent", code=302)

@app.get("/sms-consent/")
def sms_consent_public_alias_slash():
    return redirect("/sms-consent", code=301)

@app.get("/resident/sms-consent")
def sms_consent():
    return """
    <html>
        <head>
            <title>SMS Consent - Downtown Women’s Center</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; line-height: 1.6;">
            <h2>SMS Updates from Downtown Women’s Center</h2>

            <p>
                To receive SMS updates regarding shelter leave approvals, transportation notifications,
                and service reminders, text <strong>JOIN</strong> to <strong>+1 806 639 4503</strong>.
            </p>

            <p>
                Message frequency varies. Message and data rates may apply.
                Reply STOP to opt out. Reply HELP for help.
            </p>

            <p>
                <a href="/privacy">Privacy Policy</a><br>
                <a href="/terms">Terms and Conditions</a>
            </p>
        </body>
    </html>
    """

@app.route("/resident/consent", methods=["GET", "POST"])
def resident_consent():
    init_db()

    next_url = (request.args.get("next") or request.form.get("next") or "").strip()

    allowed_next = {
        url_for("resident_leave"),
        url_for("resident_transport"),
        url_for("resident_portal.home"),
    }

    if next_url not in allowed_next:
        next_url = url_for("resident_portal.home")

    resident_id = session.get("resident_id")
    shelter = session.get("resident_shelter") or ""

    if not resident_id or shelter not in SHELTERS:
        flash("Please sign in again.", "error")
        return redirect(url_for("resident_signin", next=next_url))

    if request.method == "GET":
        return render_template("resident_consent.html", next=next_url)

    choice = (request.form.get("choice") or "").strip().lower()
    if choice not in ["accept", "decline"]:
        flash("Select accept or decline.", "error")
        return render_template("resident_consent.html", next=next_url), 400

    now = utcnow_iso()
    kind = g.get("db_kind")

    if choice == "accept":
        session["sms_consent_done"] = True
        session["sms_opt_in"] = True

        db_execute(
            """
            UPDATE residents
            SET sms_opt_in = %s,
                sms_opt_in_at = %s,
                sms_opt_in_source = %s,
                sms_opt_out_at = NULL,
                sms_opt_out_source = NULL
            WHERE id = %s AND shelter = %s
            """
            if kind == "pg"
            else """
            UPDATE residents
            SET sms_opt_in = ?,
                sms_opt_in_at = ?,
                sms_opt_in_source = ?,
                sms_opt_out_at = NULL,
                sms_opt_out_source = NULL
            WHERE id = ? AND shelter = ?
            """,
            (True if kind == "pg" else 1, now, "resident_kiosk_web_form", resident_id, shelter)
        )

    else:
        session["sms_consent_done"] = True
        session["sms_opt_in"] = False

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
            (False if kind == "pg" else 0, now, "resident_kiosk_web_form_decline", resident_id, shelter)
        )

    return redirect(next_url)

@app.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    init_db()

    if request.method == "GET":
        return render_template("staff_login.html", all_shelters=SHELTERS)

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()

    ip = _client_ip()
    u = (username or "").strip().lower()

    if _rate_limited(f"staff_login_ip:{ip}", 10, 60) or _rate_limited(f"staff_login_user:{u}", 20, 3600):
        flash("Too many login attempts. Please wait and try again.", "error")
        return render_template("staff_login.html"), 429

    row = db_fetchone(
        "SELECT * FROM staff_users WHERE username = %s" if g.get("db_kind") == "pg" else "SELECT * FROM staff_users WHERE username = ?",
        (username,),
    )

    if not row:
        flash("Invalid login.", "error")
        return render_template("staff_login.html"), 401

    is_active = bool(row["is_active"] if isinstance(row, dict) else row[4])
    pw_hash = row["password_hash"] if isinstance(row, dict) else row[2]

    if not is_active or not check_password_hash(pw_hash, password):
        flash("Invalid login.", "error")
        return render_template("staff_login.html"), 401

    shelter = (request.form.get("shelter") or "").strip()
    if shelter not in SHELTERS:
        flash("Select a valid shelter.", "error")
        return render_template("staff_login.html"), 400

    session.clear()
    session["staff_user_id"] = row["id"] if isinstance(row, dict) else row[0]
    session["username"] = row["username"] if isinstance(row, dict) else row[1]
    session["role"] = row["role"] if isinstance(row, dict) else row[3]
    session["shelter"] = shelter
    session.permanent = True

    log_action("auth", None, None, session["staff_user_id"], "login", f"Staff login: {session['username']}")
    return redirect(url_for("attendance.staff_attendance"))


@app.route("/staff/logout")
@require_login
def staff_logout():
    staff_id = session.get("staff_user_id")
    log_action("auth", None, None, staff_id, "logout", f"Staff logout: {session.get('username')}")
    session.clear()
    return redirect(url_for("staff_login"))


@app.route("/staff/select-shelter", methods=["GET", "POST"])
@require_login
def staff_select_shelter():
    if request.method == "GET":
        return render_template("staff_select_shelter.html", shelters=SHELTERS)

    shelter = (request.form.get("shelter") or "").strip()
    if shelter not in SHELTERS:
        flash("Select a valid shelter.", "error")
        return redirect(url_for("staff_select_shelter"))

    session["shelter"] = shelter

    nxt = (request.form.get("next") or "").strip()
    if nxt and nxt.startswith("/staff"):
        return redirect(nxt)

    return redirect(url_for("staff_home"))


@app.route("/staff")
@require_login
@require_shelter
def staff_home():
    return redirect(url_for("attendance.staff_attendance"))

# ---- Staff Transport ----



# ---- Staff Attendance ----

@app.route("/staff/sms-consent")
@require_login
def staff_sms_consent():
    try:
        init_db()

        rows_raw = db_fetchall(
            """
            SELECT id, first_name, last_name, phone, sms_opt_in, sms_opt_out_at
            FROM residents
            WHERE phone IS NOT NULL AND phone != ''
            ORDER BY last_name ASC, first_name ASC, id DESC
            LIMIT 500
            """
        )

        rows = []
        for r in rows_raw or []:
            if isinstance(r, dict):
                rows.append(r)
            else:
                rows.append(
                    {
                        "id": r[0],
                        "first_name": r[1],
                        "last_name": r[2],
                        "phone": r[3],
                        "sms_opt_in": r[4],
                        "sms_opt_out_at": r[5],
                    }
                )

        return render_template(
            "staff_sms_consent.html",
            rows=rows,
            title="SMS Consent",
        )

    except Exception as e:
        return "SMS consent error: " + str(e), 500
  
# ---- Kiosk ----

@app.route("/kiosk/<shelter>/checkout", methods=["GET", "POST"])
def kiosk_checkout(shelter: str):
    if shelter not in SHELTERS:
        return "Invalid shelter", 404

    init_db()

    if KIOSK_PIN:
        if session.get(f"kiosk_authed_{shelter}") is not True:
            ip = _client_ip()

            # Rate limit by IP and by shelter to slow brute-force attempts
            # even when clients rotate IP addresses.
            if _rate_limited(f"kiosk_pin_ip:{ip}", 10, 300) or _rate_limited(f"kiosk_pin_shelter:{shelter}", 40, 300):
                flash("Too many PIN attempts. Please wait and try again.", "error")
                return render_template("kiosk_pin.html", shelter=shelter), 429

            if request.method == "POST":
                entered_pin = (request.form.get("kiosk_pin") or "").strip()

                # Constant-time comparison for secret values.
                if secrets.compare_digest(entered_pin, KIOSK_PIN):
                    session[f"kiosk_authed_{shelter}"] = True
                    session.permanent = True
                    return redirect(url_for("kiosk_checkout", shelter=shelter))

                flash("Invalid PIN.", "error")

            return render_template("kiosk_pin.html", shelter=shelter), 401

    if request.method == "GET":
        return render_template("kiosk_checkout.html", shelter=shelter)

    resident_code = (request.form.get("resident_code") or "").strip()
    destination = (request.form.get("destination") or "").strip()
    expected_back = (request.form.get("expected_back_time") or "").strip()
    note = (request.form.get("note") or "").strip()

    ip = _client_ip()
    code_key = resident_code if resident_code else "blank"

    if _rate_limited(f"kiosk_checkout_ip:{ip}", 60, 60) or _rate_limited(f"kiosk_checkout_code:{code_key}", 20, 3600):
        flash("Too many attempts. Please wait and try again.", "error")
        return render_template("kiosk_checkout.html", shelter=shelter), 429

    errors = []

    if (not resident_code.isdigit()) or (len(resident_code) != 8):
        errors.append("Enter an 8 digit Resident Code.")

    if not destination:
        errors.append("Destination is required.")

    if not expected_back:
        errors.append("Expected back time is required.")

    row = db_fetchone(
        "SELECT id FROM residents WHERE shelter = %s AND resident_code = %s AND is_active = TRUE"
        if g.get("db_kind") == "pg"
        else "SELECT id FROM residents WHERE shelter = ? AND resident_code = ? AND is_active = 1",
        (shelter, resident_code),
    )

    if not row:
        errors.append("Invalid Resident Code.")

    expected_back_value = None
    if expected_back:
        try:
            local_dt = datetime.fromisoformat(expected_back).replace(tzinfo=ZoneInfo("America/Chicago"))
            expected_back_value = local_dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
        except Exception:
            errors.append("Invalid expected back time.")

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("kiosk_checkout.html", shelter=shelter), 400

    resident_id = int(row["id"] if isinstance(row, dict) else row[0])

    full_note = f"Destination: {destination}"
    if note:
        full_note = f"{full_note} | Note: {note}"

    sql = (
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    db_execute(
        sql,
        (resident_id, shelter, "check_out", utcnow_iso(), None, full_note, expected_back_value),
    )

    log_action("attendance", resident_id, shelter, None, "kiosk_check_out", f"expected_back={expected_back_value or ''} {full_note}".strip())
    flash("Checked out.", "ok")
    return redirect(url_for("kiosk_checkout", shelter=shelter))
@app.route("/staff/admin/users", methods=["GET", "POST"])
@require_login
@require_admin
def admin_users():
    init_db()

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        role = (request.form.get("role") or "staff").strip()

        if not username or not password:
            flash("Username and password required.", "error")
            return redirect(url_for("admin_users"))

        if len(password) < MIN_STAFF_PASSWORD_LEN:
            flash(f"Password must be at least {MIN_STAFF_PASSWORD_LEN} characters.", "error")
            return redirect(url_for("admin_users"))

        if role not in USER_ROLES:
            flash("Invalid role.", "error")
            return redirect(url_for("admin_users"))

        try:
            db_execute(
                "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (%s, %s, %s, %s, %s)"
                if g.get("db_kind") == "pg"
                else "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, generate_password_hash(password), role, True, utcnow_iso()),
            )
            flash("User created.", "ok")
        except Exception:
            flash("Username already exists.", "error")

        return redirect(url_for("admin_users"))

    users = db_fetchall("SELECT id, username, role, is_active, created_at FROM staff_users ORDER BY created_at DESC")

    return render_template("admin_users.html", users=users, fmt_dt=fmt_dt, roles=sorted(USER_ROLES), ROLE_LABELS=ROLE_LABELS)


@app.route("/admin/delete-user/<username>", methods=["POST"])
@require_login
@require_admin
def delete_user(username):
    if username == session.get("username"):
        flash("You cannot delete yourself.", "error")
        return redirect(url_for("admin_users"))

    db_execute(
        "DELETE FROM staff_users WHERE username = %s" if g.get("db_kind") == "pg" else "DELETE FROM staff_users WHERE username = ?",
        (username,),
    )

    log_action("staff_user", None, None, session.get("staff_user_id"), "delete_user", f"deleted_username={username}")
    flash(f"User '{username}' deleted.", "ok")
    return redirect(url_for("admin_users"))

# ---- Audit ----

def _audit_where_from_request():
    kind = g.get("db_kind")
    where = []
    params = []

    def add_eq(field, key):
        v = (request.args.get(key) or "").strip()
        if v:
            where.append(f"{field} = " + ("%s" if kind == "pg" else "?"))
            params.append(v)

    add_eq("a.shelter", "shelter")
    add_eq("a.entity_type", "entity_type")
    add_eq("a.action_type", "action_type")

    staff_user_id = (request.args.get("staff_user_id") or "").strip()
    if staff_user_id.isdigit():
        where.append("a.staff_user_id = " + ("%s" if kind == "pg" else "?"))
        params.append(int(staff_user_id))

    q = (request.args.get("q") or "").strip()
    if q:
        like_op = "ILIKE" if kind == "pg" else "LIKE"
        ph = "%s" if kind == "pg" else "?"
        where.append(
            "("
            f"CAST(a.id AS TEXT) {like_op} {ph} OR "
            f"COALESCE(a.action_details, '') {like_op} {ph} OR "
            f"COALESCE(a.action_type, '') {like_op} {ph} OR "
            f"COALESCE(a.entity_type, '') {like_op} {ph} OR "
            f"COALESCE(su.username, '') {like_op} {ph}"
            ")"
        )
        pat = f"%{q}%"
        params.extend([pat, pat, pat, pat, pat])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    return where_sql, tuple(params)


@app.route("/staff/admin/audit-log")
@require_login
@require_admin
def staff_audit_log():
    params = ()

    sql = (
        """
        SELECT a.*, su.username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        ORDER BY a.id DESC
        LIMIT %s
        """
        if current_app.config.get("DATABASE_URL")
        else """
        SELECT a.*, su.username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        ORDER BY a.id DESC
        LIMIT ?
        """
    )

    rows = db_fetchall(sql, params + (200,))

    return render_template(
        "staff_audit_log.html",
        rows=rows,
    )


@app.get("/staff/admin/audit-log/csv")
@require_login
@require_shelter
@require_admin
def staff_audit_log_csv():
    created_expr = "a.created_at::text" if g.get("db_kind") == "pg" else "a.created_at"
    where_sql, params = _audit_where_from_request()

    sql = (
        f"SELECT a.id, a.entity_type, a.entity_id, a.shelter, "
        f"COALESCE(su.username, '') AS staff_username, "
        f"a.action_type, COALESCE(a.action_details, '') AS action_details, "
        f"{created_expr} AS created_at "
        f"FROM audit_log a "
        f"LEFT JOIN staff_users su ON su.id = a.staff_user_id "
        f"{where_sql} "
        f"ORDER BY a.id DESC"
    )

    rows = db_fetchall(sql, params)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "entity_type", "entity_id", "shelter", "staff_username", "action_type", "action_details", "created_at"])

    for r in rows:
        if isinstance(r, dict):
            w.writerow([
                r.get("id", ""),
                r.get("entity_type", ""),
                r.get("entity_id", ""),
                r.get("shelter", ""),
                r.get("staff_username", ""),
                r.get("action_type", ""),
                r.get("action_details", ""),
                r.get("created_at", ""),
            ])
        else:
            w.writerow(list(r))

    data = buf.getvalue()
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )

# ---- Residents ----

@app.get("/staff/residents")
@require_login
@require_shelter
@require_staff_or_admin
def staff_residents():
    init_db()
    shelter = session["shelter"]

    show = (request.args.get("show") or "active").strip().lower()

    if show == "all":
        residents = db_fetchall(
            """
            SELECT *
            FROM residents
            WHERE shelter = %s
            ORDER BY is_active DESC, last_name ASC, first_name ASC
            """
            if g.get("db_kind") == "pg"
            else """
            SELECT *
            FROM residents
            WHERE shelter = ?
            ORDER BY is_active DESC, last_name ASC, first_name ASC
            """,
            (shelter,),
        )
    else:
        residents = db_fetchall(
            """
            SELECT *
            FROM residents
            WHERE shelter = %s AND is_active = TRUE
            ORDER BY last_name ASC, first_name ASC
            """
            if g.get("db_kind") == "pg"
            else """
            SELECT *
            FROM residents
            WHERE shelter = ? AND is_active = 1
            ORDER BY last_name ASC, first_name ASC
            """,
            (shelter,),
        )

    return render_template("staff_residents.html", residents=residents, shelter=shelter, show=show)


@app.post("/staff/residents")
@require_login
@require_shelter
@require_resident_create
def staff_residents_post():
    init_db()
    shelter = session["shelter"]

    first = (request.form.get("first_name") or "").strip()
    last = (request.form.get("last_name") or "").strip()

    if not first or not last:
        flash("First and last name required.", "error")
        return redirect(url_for("staff_residents"))

    resident_code = generate_resident_code()
    resident_identifier = generate_resident_identifier()

    db_execute(
        "INSERT INTO residents (resident_identifier, resident_code, first_name, last_name, shelter, is_active, created_at) "
        + ("VALUES (%s, %s, %s, %s, %s, %s, %s)" if g.get("db_kind") == "pg" else "VALUES (?, ?, ?, ?, ?, ?, ?)"),
        (resident_identifier, resident_code, first, last, shelter, True, utcnow_iso()),
    )

    log_action("resident", None, shelter, session.get("staff_user_id"), "create", f"code={resident_code} {first} {last}")
    flash("Resident created.", "ok")
    return redirect(url_for("staff_residents"))


@app.route("/staff/residents/<int:resident_id>/transfer", methods=["GET", "POST"])
@require_login
@require_shelter
@require_transfer
def staff_resident_transfer(resident_id: int):
    init_db()

    resident = db_fetchone(
        "SELECT * FROM residents WHERE id = %s AND shelter = %s" if g.get("db_kind") == "pg" else "SELECT * FROM residents WHERE id = ? AND shelter = ?",
        (resident_id, session["shelter"]),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("staff_residents"))

    from_shelter = resident["shelter"] if isinstance(resident, dict) else resident[1]

    if request.method == "POST":
        to_shelter = (request.form.get("to_shelter") or "").strip()
        note = (request.form.get("note") or "").strip()

        if to_shelter not in SHELTERS:
            flash("Select a valid shelter.", "error")
            return redirect(url_for("staff_resident_transfer", resident_id=resident_id))

        if to_shelter == from_shelter:
            flash("Resident is already at that shelter.", "error")
            return redirect(url_for("staff_resident_transfer", resident_id=resident_id))

        record_resident_transfer(resident_id=resident_id, from_shelter=from_shelter, to_shelter=to_shelter, note=note)

        db_execute(
            """
            INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else """
            INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                resident_id,
                from_shelter,
                "check_out",
                utcnow_iso(),
                session.get("staff_user_id"),
                f"Transferred to {to_shelter}. {note}".strip(),
            ),
        )

        resident_identifier = resident["resident_identifier"] if isinstance(resident, dict) else resident[2]

        db_execute(
            """
            UPDATE leave_requests
            SET shelter = %s
            WHERE shelter = %s AND resident_identifier = %s AND status = 'pending'
            """
            if g.get("db_kind") == "pg"
            else """
            UPDATE leave_requests
            SET shelter = ?
            WHERE shelter = ? AND resident_identifier = ? AND status = 'pending'
            """,
            (to_shelter, from_shelter, resident_identifier),
        )

        db_execute(
            """
            UPDATE transport_requests
            SET shelter = %s
            WHERE shelter = %s AND resident_identifier = %s AND status = 'pending'
            """
            if g.get("db_kind") == "pg"
            else """
            UPDATE transport_requests
            SET shelter = ?
            WHERE shelter = ? AND resident_identifier = ? AND status = 'pending'
            """,
            (to_shelter, from_shelter, resident_identifier),
        )

        db_execute(
            "UPDATE residents SET shelter = %s WHERE id = %s" if g.get("db_kind") == "pg" else "UPDATE residents SET shelter = ? WHERE id = ?",
            (to_shelter, resident_id),
        )

        flash(f"Resident transferred from {from_shelter} to {to_shelter}.", "ok")
        return redirect(url_for("staff_residents"))

    return render_template(
        "staff_resident_transfer.html",
        resident=resident,
        from_shelter=from_shelter,
        shelters=[s for s in SHELTERS if s != from_shelter],
    )


@app.route("/staff/residents/<int:resident_id>/set-active", methods=["POST"])
@require_login
@require_shelter
@require_staff_or_admin
def staff_resident_set_active(resident_id: int):
    init_db()
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]
    active = (request.form.get("active") or "").strip()

    if active not in ["0", "1"]:
        flash("Invalid action.", "error")
        return redirect(url_for("staff_residents"))

    if g.get("db_kind") == "pg":
        db_execute("UPDATE residents SET is_active = %s WHERE id = %s AND shelter = %s", (active == "1", resident_id, shelter))
    else:
        db_execute("UPDATE residents SET is_active = ? WHERE id = ? AND shelter = ?", (1 if active == "1" else 0, resident_id, shelter))

    log_action("resident", resident_id, shelter, staff_id, "set_active", f"active={active}")
    flash("Updated.", "ok")
    return redirect(url_for("staff_residents"))

# ---- Dangerous Admin Maintenance ----

@app.route("/admin/wipe-all-data", methods=["POST"])
@require_login
@require_admin
def wipe_all_data():
    if not ENABLE_DANGEROUS_ADMIN_ROUTES:
        abort(404)

    init_db()

    db_execute("TRUNCATE TABLE attendance_events RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM attendance_events")
    db_execute("TRUNCATE TABLE leave_requests RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM leave_requests")
    db_execute("TRUNCATE TABLE transport_requests RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM transport_requests")
    db_execute("TRUNCATE TABLE residents RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM residents")
    db_execute("TRUNCATE TABLE audit_log RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM audit_log")

    log_action("admin", None, None, session.get("staff_user_id"), "wipe_all_data", "Wiped attendance, leave, transport, residents, audit_log")
    return "All non staff data wiped."


@app.route("/admin/recreate-schema", methods=["POST"])
@require_login
@require_admin
def recreate_schema():
    if not ENABLE_DANGEROUS_ADMIN_ROUTES:
        abort(404)

    init_db()

    if g.get("db_kind") == "pg":
        db_execute("DROP TABLE IF EXISTS attendance_events CASCADE")
        db_execute("DROP TABLE IF EXISTS leave_requests CASCADE")
        db_execute("DROP TABLE IF EXISTS transport_requests CASCADE")
        db_execute("DROP TABLE IF EXISTS residents CASCADE")
        db_execute("DROP TABLE IF EXISTS audit_log CASCADE")
        db_execute("DROP TABLE IF EXISTS resident_transfers CASCADE")
        db_execute("DROP TABLE IF EXISTS rate_limit_events CASCADE")
    else:
        db_execute("DROP TABLE IF EXISTS attendance_events")
        db_execute("DROP TABLE IF EXISTS leave_requests")
        db_execute("DROP TABLE IF EXISTS transport_requests")
        db_execute("DROP TABLE IF EXISTS residents")
        db_execute("DROP TABLE IF EXISTS audit_log")
        db_execute("DROP TABLE IF EXISTS resident_transfers")

    init_db()
    log_action("admin", None, None, session.get("staff_user_id"), "recreate_schema", "Dropped and recreated tables")
    return "Schema recreated."

@app.get("/resident/login")
def resident_login_alias():
    return redirect("/resident", code=302)

@app.get("/resident/login/")
def resident_login_alias_slash():
    return redirect("/resident", code=301)

@app.get("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.ico"), code=301)

@app.get("/health")
def health():
    return {"status": "ok"}, 200

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




































