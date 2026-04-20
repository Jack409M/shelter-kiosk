from __future__ import annotations

from flask import Blueprint

resident_portal = Blueprint("resident_portal", __name__)


def _register_route_parts() -> None:
    from routes.resident_portal_parts import budget, chores, daily_log, home  # noqa: F401


_register_route_parts()
