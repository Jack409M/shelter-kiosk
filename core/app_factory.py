from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import secrets
from datetime import timedelta

from flask import Blueprint, Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from core.app_hooks import register_app_hooks
from core.db import close_db
from core.helpers import (
    fmt_date,
    fmt_dt,
    fmt_pretty_date,
    fmt_pretty_dt,
    fmt_time_only,
    safe_url_for,
    shelter_display,
    utcnow_iso,
)
from core.rate_limit import ban_ip, is_ip_banned, is_rate_limited
from core.request_security import register_request_security
from core.request_utils import client_ip
from core.runtime import init_db
from routes.resident_parts.consent import resident_consent_view


# ------------------------------------------------------------
# Blueprint loader
# ------------------------------------------------------------
def register_blueprints(app: Flask) -> None:
    import routes

    for _, module_name, _ in pkgutil.iter_modules(routes.__path__):
        module = importlib.import_module(f"routes.{module_name}")

        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, Blueprint) and obj.name not in app.blueprints:
                app.register_blueprint(obj)


# ------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------
def _client_ip() -> str:
    return client_ip()


def _csrf_token() -> str:
    tok = session.get("_csrf_token")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf_token"] = tok
    return tok


def _register_csrf(app: Flask) -> None:
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


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("404.html"), 404


def _configure_app(app: Flask) -> None:
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    app.config["DATABASE_URL"] = (os.getenv("DATABASE_URL") or "").strip() or None
    app.config["CLOUDFLARE_ONLY"] = os.getenv("CLOUDFLARE_ONLY", "")
    app.config["ADMIN_USERNAME"] = os.environ.get("ADMIN_USERNAME")
    app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD")
    app.config["INIT_DB_FUNC"] = init_db
    app.config["UTCNOW_ISO_FUNC"] = utcnow_iso

    secret = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
    if not secret:
        raise RuntimeError("FLASK_SECRET_KEY is required and must be set in the environment.")

    app.secret_key = secret
    app.permanent_session_lifetime = timedelta(hours=8)

    cookie_secure = (os.environ.get("COOKIE_SECURE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    app.config.update(
        SESSION_COOKIE_SECURE=cookie_secure,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )


def _register_template_helpers(app: Flask) -> None:
    app.jinja_env.globals["safe_url_for"] = safe_url_for
    app.jinja_env.globals["shelter_display"] = shelter_display
    app.jinja_env.filters["shelter"] = shelter_display
    app.jinja_env.filters["app_date"] = fmt_date
    app.jinja_env.filters["app_dt"] = fmt_dt
    app.jinja_env.filters["app_time"] = fmt_time_only
    app.jinja_env.filters["app_pretty_date"] = fmt_pretty_date
    app.jinja_env.filters["app_pretty_dt"] = fmt_pretty_dt


def _register_context_processors(app: Flask) -> None:
    @app.context_processor
    def inject_current_clock():
        return {
            "utcnow_iso": utcnow_iso,
        }


# ------------------------------------------------------------
# Application factory
# ------------------------------------------------------------
def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    _configure_app(app)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    app.logger.setLevel(logging.DEBUG)

    _register_template_helpers(app)

    app.teardown_appcontext(close_db)

    register_request_security(
        app,
        client_ip_func=_client_ip,
        is_ip_banned_func=is_ip_banned,
        is_rate_limited_func=is_rate_limited,
        ban_ip_func=ban_ip,
    )

    _register_csrf(app)
    _register_error_handlers(app)
    _register_context_processors(app)

    register_blueprints(app)
    register_app_hooks(app)

    return app
