from __future__ import annotations

import importlib
import os

from flask import Flask


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

    app = Flask(__name__)

    # Load environment configuration
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")

    # Register route blueprints
    register_blueprints(app)

    return app
