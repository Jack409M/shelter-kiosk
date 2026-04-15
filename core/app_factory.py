from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import secrets
from datetime import timedelta
from typing import Any

from flask import Blueprint, Flask, flash, redirect, request, session, url_for
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
from core.pass_retention_scheduler import start_pass_retention_scheduler
from core.rate_limit import ban_ip, is_ip_banned, is_rate_limited
from core.request_security import register_request_security
from core.request_utils import client_ip
from core.runtime import (
    database_mode_label_from_url,
    init_db,
    load_runtime_config,
)

CSRF_EXEMPT_ENDPOINTS = {
    "resident_requests.sms_consent",
    "twilio.twilio_inbound",
    "twilio.twilio_status",
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


def _resolve_session_cookie_secure(app: Flask) -> bool:
    cookie_secure_env = (os.environ.get("COOKIE_SECURE") or "").strip()
    if cookie_secure_env:
        return cookie_secure_env.lower() in TRUTHY_ENV_VALUES

    if app.config.get("TESTING") or app.config.get("DEBUG"):
        return False

    return True


def _resolve_session_cookie_name(session_cookie_secure: bool) -> str:
    if session_cookie_secure:
        return "__Host-shelter_session"
    return "shelter_session"


def _configure_app(app: Flask, test_config: dict[str, Any] | None = None) -> None:
    explicit_database_url = None
    if test_config and "DATABASE_URL" in test_config:
        explicit_database_url = str(test_config["DATABASE_URL"] or "").strip()

    runtime_config = load_runtime_config(explicit_database_url=explicit_database_url)

    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    app.config["DATABASE_URL"] = runtime_config.database_url
    app.config["DATABASE_MODE_LABEL"] = runtime_config.database_mode_label
    app.config["CLOUDFLARE_ONLY"] = os.getenv("CLOUDFLARE_ONLY", "")
    app.config["ADMIN_USERNAME"] = os.environ.get("ADMIN_USERNAME")
    app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD")
    app.config["INIT_DB_FUNC"] = init_db
    app.config["UTCNOW_ISO_FUNC"] = utcnow_iso

    if test_config:
        app.config.update(test_config)

    final_database_url = str(app.config.get("DATABASE_URL") or "").strip()
    if not final_database_url:
        raise RuntimeError("DATABASE_URL is required.")

    app.config["DATABASE_URL"] = final_database_url
    app.config["DATABASE_MODE_LABEL"] = database_mode_label_from_url(final_database_url)

    secret = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
    if not secret:
        raise RuntimeError("FLASK_SECRET_KEY is required and must be set in the environment.")

    app.secret_key = secret
    app.permanent_session_lifetime = timedelta(hours=8)

    session_cookie_secure = _resolve_session_cookie_secure(app)
    session_cookie_name = _resolve_session_cookie_name(session_cookie_secure)

    app.config.update(
        SESSION_COOKIE_NAME=session_cookie_name,
        SESSION_COOKIE_SECURE=session_cookie_secure,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_REFRESH_EACH_REQUEST=False,
    )


def _configure_proxy(app: Flask) -> None:
    proxy_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    app.wsgi_app = proxy_app  # type: ignore[method-assign]


def _configure_logging(app: Flask) -> str:
    log_level_name = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    app.logger.setLevel(log_level)

    app.logger.info("Shelter Kiosk starting")
    app.logger.info(
        "database_mode=%s cloudflare_only=%s log_level=%s",
        app.config.get("DATABASE_MODE_LABEL"),
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
        return None


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


def _close_db_teardown(exc: BaseException | None = None) -> None:
    close_db(exc if isinstance(exc, Exception) else None)


def _register_core_services(app: Flask) -> None:
    _register_template_helpers(app)
    app.teardown_appcontext(_close_db_teardown)
    _register_security(app)
    _register_csrf(app)
    _register_context_processors(app)


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    _configure_app(app, test_config=test_config)
    _configure_proxy(app)
    _configure_logging(app)

    with app.app_context():
        init_db()

    _register_core_services(app)
    register_blueprints(app)
    register_app_hooks(app)
    start_pass_retention_scheduler(app)

    app.logger.info(
        "blueprints_loaded=%s count=%s",
        sorted(app.blueprints.keys()),
        len(app.blueprints),
    )

    return app
