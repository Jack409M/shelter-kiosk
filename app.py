
from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import secrets

from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

from flask import (
    Flask,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix

from core.auth import require_login
from core.auth import require_shelter
from core.db import close_db, db_fetchall, get_db
from core.helpers import (
    fmt_date,
    fmt_dt,
    fmt_pretty_date,
    fmt_pretty_dt,
    fmt_time_only,
    safe_url_for,
    utcnow_iso,
)
from core.rate_limit import ban_ip, is_ip_banned, is_rate_limited
from core.request_security import register_request_security
from core.request_utils import client_ip
from core.shelters import get_all_shelters as load_all_shelters
from db import schema

try:
    from twilio.request_validator import RequestValidator
    from twilio.rest import Client
except Exception:
    Client = None
    RequestValidator = None


# ------------------------------------------------------------
# Environment flags and constants
# ------------------------------------------------------------
# Future extraction note
# These environment values should eventually move into core.config
# so this file becomes app wiring only.

TWILIO_ENABLED = os.environ.get("TWILIO_ENABLED", "false").lower() == "true"
TWILIO_INBOUND_ENABLED = (os.environ.get("TWILIO_INBOUND_ENABLED", "false").strip().lower() == "true")
TWILIO_STATUS_ENABLED = (os.environ.get("TWILIO_STATUS_ENABLED", "false").strip().lower() == "true")
TWILIO_STATUS_CALLBACK_URL = (os.environ.get("TWILIO_STATUS_CALLBACK_URL") or "").strip()

MIN_STAFF_PASSWORD_LEN = 8

USER_ROLES = {"admin", "shelter_director", "staff", "case_manager", "ra"}

ROLE_LABELS = {
    "admin": "Admin",
    "shelter_director": "Shelter Director",
    "staff": "Staff",
    "ra": "RA DESK",
    "case_manager": "Case Mgr",
}

STAFF_ROLES = {"admin", "shelter_director", "staff", "case_manager", "ra"}
TRANSFER_ROLES = {"admin", "shelter_director", "case_manager"}

APP_DIR = os.path.abspath(os.path.dirname(__file__))
SQLITE_PATH = os.path.join(APP_DIR, "shelter_operations.db")

DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
ENABLE_DEBUG_ROUTES = (os.environ.get("ENABLE_DEBUG_ROUTES") or "").strip().lower() in {"1", "true", "yes", "on"}
KIOSK_PIN = (os.environ.get("KIOSK_PIN") or "").strip()
ENABLE_DANGEROUS_ADMIN_ROUTES = (os.environ.get("ENABLE_DANGEROUS_ADMIN_ROUTES") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL")
app.config["SQLITE_PATH"] = os.environ.get("SQLITE_PATH", SQLITE_PATH)
app.config["CLOUDFLARE_ONLY"] = os.environ.get("CLOUDFLARE_ONLY", "")
app.jinja_env.globals["safe_url_for"] = safe_url_for
app.jinja_env.filters["app_date"] = fmt_date
app.jinja_env.filters["app_dt"] = fmt_dt
app.jinja_env.filters["app_time"] = fmt_time_only
app.jinja_env.filters["app_pretty_date"] = fmt_pretty_date
app.jinja_env.filters["app_pretty_dt"] = fmt_pretty_dt
app.teardown_appcontext(close_db)
app.logger.setLevel(logging.DEBUG)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)


# ------------------------------------------------------------
# Blueprint registration
# ------------------------------------------------------------
# Future extraction note
# This can eventually move into a dedicated app factory module
# after more setup code is extracted from this file.
def register_blueprints(app: Flask) -> None:
    import routes
    from flask import Blueprint

    for _, module_name, _ in pkgutil.iter_modules(routes.__path__):
        module = importlib.import_module(f"routes.{module_name}")

        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, Blueprint) and obj.name not in app.blueprints:
                app.register_blueprint(obj)


# ------------------------------------------------------------
# Request utility delegation
# ------------------------------------------------------------
# Future extraction note
# Additional request parsing helpers can move into core.request_utils.
def _client_ip() -> str:
    return client_ip()


register_blueprints(app)

# Centralized request security middleware now lives in core.request_security.
# Keep request level defense registered here, but keep the actual logic out
# of app.py so this file does not become a god file again.
register_request_security(
    app,
    client_ip_func=_client_ip,
    is_ip_banned_func=is_ip_banned,
    is_rate_limited_func=is_rate_limited,
    ban_ip_func=ban_ip,
)


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


@app.before_request
def force_https_redirect():
    if current_app.debug:
        return None

    if request.headers.get("X-Forwarded-Proto", "").lower() == "https":
        return None

    if request.is_secure:
        return None

    return redirect(request.url.replace("http://", "https://", 1), code=301)


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


# ------------------------------------------------------------
# CSRF
# ------------------------------------------------------------
# Future extraction note
# These CSRF helpers can move into core.csrf later.
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
        "forms_ingest.jotform_webhook",
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


# ------------------------------------------------------------
# Shelter helpers
# ------------------------------------------------------------
# Future extraction note
# Additional shelter query helpers can move into core.shelters.
def get_all_shelters() -> list[str]:
    return load_all_shelters(init_db)


@app.context_processor
def inject_shelters():
    return {
        "all_shelters": get_all_shelters(),
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
        if g.get("db_kind") == "pg"
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


# ------------------------------------------------------------
# Database initialization
# ------------------------------------------------------------
# Current state
# schema mutations and indexes are mostly delegated to db/schema.py.
# Future extraction targets
# 1. move remaining initialization wiring into db/schema.py
# 2. collapse legacy_init_db into schema.init_db once callers are aligned
def legacy_init_db() -> None:
    get_db()
    schema.init_db()


init_db = legacy_init_db
app.config["INIT_DB_FUNC"] = init_db
app.config["UTCNOW_ISO_FUNC"] = utcnow_iso
app.config["ADMIN_USERNAME"] = os.environ.get("ADMIN_USERNAME")
app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD")


# ------------------------------------------------------------
# Decorators
# ------------------------------------------------------------
# Future extraction note
# These should eventually move into core.decorators.
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
            return redirect(safe_url_for("residents.staff_residents") or url_for("auth.staff_home"))
        return fn(*args, **kwargs)

    return wrapper


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.after_request
def add_cache_headers(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    else:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")

    csp = (
        "default-src 'self'; "
        "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; "
        "connect-src 'self'; "
        "font-src 'self' data: https://unpkg.com; "
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

