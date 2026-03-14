from __future__ import annotations

import importlib
import logging
import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from core.db import close_db
from core.helpers import (
    safe_url_for,
    fmt_date,
    fmt_dt,
    fmt_time_only,
    fmt_pretty_date,
    fmt_pretty_dt,
)


# ------------------------------------------------------------
# Blueprint loader
# ------------------------------------------------------------
def register_blueprints(app: Flask) -> None:
    """
    Automatically load all route blueprints inside /routes.

    Each module must expose a variable named `bp` or `admin`
    which is the Flask Blueprint instance.
    """

    routes_dir = os.path.join(os.path.dirname(__file__), "..", "routes")

    for filename in os.listdir(routes_dir):
        if not filename.endswith(".py"):
            continue

        if filename.startswith("_"):
            continue

        module_name = filename[:-3]
        module = importlib.import_module(f"routes.{module_name}")

        if hasattr(module, "bp"):
            app.register_blueprint(module.bp)
        elif hasattr(module, "admin"):
            app.register_blueprint(module.admin)


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

    return app
