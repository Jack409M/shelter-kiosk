from __future__ import annotations

import importlib
import logging
import os
import pkgutil

from flask import Blueprint, Flask
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
)


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
# Application factory
# ------------------------------------------------------------
def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    # ------------------------------------------------------------
    # Basic configuration
    # ------------------------------------------------------------
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL")

    # Trust Cloudflare proxy headers
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # Logging
    app.logger.setLevel(logging.DEBUG)

    # ------------------------------------------------------------
    # Template helpers
    # ------------------------------------------------------------
    app.jinja_env.globals["safe_url_for"] = safe_url_for
    app.jinja_env.filters["app_date"] = fmt_date
    app.jinja_env.filters["app_dt"] = fmt_dt
    app.jinja_env.filters["app_time"] = fmt_time_only
    app.jinja_env.filters["app_pretty_date"] = fmt_pretty_date
    app.jinja_env.filters["app_pretty_dt"] = fmt_pretty_dt

    # ------------------------------------------------------------
    # Database teardown
    # ------------------------------------------------------------
    app.teardown_appcontext(close_db)

    # ------------------------------------------------------------
    # Register route blueprints
    # ------------------------------------------------------------
    register_blueprints(app)

    # ------------------------------------------------------------
    # Register request hooks and security headers
    # ------------------------------------------------------------
    register_app_hooks(app)

    return app
