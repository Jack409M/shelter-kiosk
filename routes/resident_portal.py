from __future__ import annotations

from importlib import import_module

from flask import Blueprint

from core.db import get_db
from core.kiosk_activity_categories import load_kiosk_activity_categories_for_shelter
from core.pass_retention import run_pass_retention_cleanup_for_shelter

resident_portal = Blueprint("resident_portal", __name__)


def _load_route_parts() -> dict[str, object]:
    return {
        "home": import_module("routes.resident_portal_parts.home"),
        "chores": import_module("routes.resident_portal_parts.chores"),
        "daily_log": import_module("routes.resident_portal_parts.daily_log"),
        "budget": import_module("routes.resident_portal_parts.budget"),
    }


_IMPORTED_PARTS = _load_route_parts()

home = _IMPORTED_PARTS["home"]
chores = _IMPORTED_PARTS["chores"]
daily_log = _IMPORTED_PARTS["daily_log"]
budget = _IMPORTED_PARTS["budget"]
