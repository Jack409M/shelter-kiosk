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

CSRF_EXEMPT_ENDPOINTS = {
    "resident_requests.sms_consent",
    "twilio.twilio_inbound",
    "twilio.twilio_status",
}

RESIDENT_SAFE_PATHS = {
    "/leave",
    "/pass-request",
    "/transport",
    "/sms-consent",
    "/sms-consent/",
}

TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def register_blueprints(app: Flask) -> None:
    import routes

    for _, module_name, _ in pkgutil.iter_modules(routes.__path__):
        module = importlib.import_module(f"routes.{module_name}")

        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, Blueprint) and obj.name not in app.blueprints:
                app.register_blueprint(obj)


def _client_ip() -> str:
    return client_ip()


def _csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in TRUTHY_ENV_VALUES


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

    app.config.update(
        SESSION_COOKIE_SECURE=_env_truthy("COOKIE_SECURE"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )


def _configure_proxy(app: Flask) -> None:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)


def _configure_logging(app: Flask) -> str:
    log_level_name = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    app.logger.setLevel(log_level)

    app.logger.info("Shelter Kiosk starting")

    if not app.config["DATABASE_URL"]:
        raise RuntimeError("DATABASE_URL is required. App is locked to Postgres.")

    app.logger.info(
        "database_mode=%s cloudflare_only=%s log_level=%s",
        "postgres",
        app.config.get("CLOUDFLARE_ONLY"),
        log_level_name,
    )

    return log_level_name


def _register_template_helpers(app: Flask) -> None:
    app.jinja_env.globals["safe_url_for"] = safe_url_for
    app.jinja_env.globals["shelter_display"] = shelter_display
    app.jinja_env.globals["csrf_token"] = _csrf_token

    app.jinja_env.filters["shelter"] = shelter_display

    app.jinja_env.filters["app_date"] = fmt_date
    app.jinja_env.filters["app_dt"] = fmt_dt
    app.jinja_env.filters["app_time"] = fmt_time_only
    app.jinja_env.filters["app_pretty_date"] = fmt_pretty_date
    app.jinja_env.filters["app_pretty_dt"] = fmt_pretty_dt

    app.jinja_env.filters["chi_date"] = fmt_date
    app.jinja_env.filters["chi_dt"] = fmt_dt
    app.jinja_env.filters["chi_time"] = fmt_time_only
    app.jinja_env.filters["chi_pretty_date"] = fmt_pretty_date
    app.jinja_env.filters["chi_pretty_dt"] = fmt_pretty_dt


def _csrf_failure_redirect():
    fallback = url_for("auth.staff_login")
    endpoint = str(request.endpoint or "")

    if endpoint.startswith("resident_") or endpoint.startswith("resident_requests."):
        fallback = url_for("resident_requests.resident_signin")

    return redirect(request.referrer or fallback)


def _register_csrf(app: Flask) -> None:
    def _csrf_protect():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None

        if request.endpoint in CSRF_EXEMPT_ENDPOINTS:
            return None

        sent_token = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token") or ""
        expected_token = session.get("_csrf_token") or ""

        if not sent_token or not expected_token or sent_token != expected_token:
            flash("Session expired. Please retry.", "error")
            return _csrf_failure_redirect()

        return None

    @app.before_request
    def _csrf_before_request():
        response = _csrf_protect()
        if response is not None:
            return response


def _is_resident_context() -> bool:
    endpoint = str(request.endpoint or "")
    path = (request.path or "").strip()

    return (
        "resident_id" in session
        or endpoint.startswith("resident_")
        or endpoint.startswith("resident_requests.")
        or endpoint.startswith("resident_portal.")
        or path == "/resident"
        or path.startswith("/resident/")
        or path in RESIDENT_SAFE_PATHS
    )


def _resident_safe_response():
    if not _is_resident_context():
        return None

    session.clear()
    flash("Your session ended. Please sign in again.", "error")
    return redirect(url_for("public.public_home"))


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def page_forbidden(error):
        resident_response = _resident_safe_response()
        if resident_response is not None:
            return resident_response
        return "Forbidden", 403

    @app.errorhandler(404)
    def page_not_found(error):
        resident_response = _resident_safe_response()
        if resident_response is not None:
            return resident_response
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        app.logger.exception("Internal server error", exc_info=error)
        resident_response = _resident_safe_response()
        if resident_response is not None:
            return resident_response
        return "Internal Server Error", 500

    @app.errorhandler(Exception)
    def unhandled_exception(error):
        app.logger.exception("Unhandled exception", exc_info=error)
        resident_response = _resident_safe_response()
        if resident_response is not None:
            return resident_response
        return "Internal Server Error", 500


def _register_context_processors(app: Flask) -> None:
    @app.context_processor
    def inject_current_clock():
        return {
            "utcnow_iso": utcnow_iso,
        }


def _register_security(app: Flask) -> None:
    register_request_security(
        app,
        client_ip_func=_client_ip,
        is_ip_banned_func=is_ip_banned,
        is_rate_limited_func=is_rate_limited,
        ban_ip_func=ban_ip,
    )


def _register_core_services(app: Flask) -> None:
    _register_template_helpers(app)
    app.teardown_appcontext(close_db)
    _register_security(app)
    _register_csrf(app)
    _register_error_handlers(app)
    _register_context_processors(app)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    _configure_app(app)
    _configure_proxy(app)
    _configure_logging(app)
    _register_core_services(app)
    register_blueprints(app)
    register_app_hooks(app)

    app.logger.info(
        "blueprints_loaded=%s count=%s",
        sorted(app.blueprints.keys()),
        len(app.blueprints),
    )

    return app
