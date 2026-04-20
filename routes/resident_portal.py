from __future__ import annotations

from importlib import import_module

from flask import Blueprint, render_template as _render_template

from core.db import get_db as _get_db
from core.kiosk_activity_categories import (
    load_active_kiosk_activity_child_options_for_shelter as _load_active_kiosk_activity_child_options_for_shelter,
    load_kiosk_activity_categories_for_shelter as _load_kiosk_activity_categories_for_shelter,
)
from core.pass_retention import (
    run_pass_retention_cleanup_for_shelter as _run_pass_retention_cleanup_for_shelter,
)

resident_portal = Blueprint("resident_portal", __name__)

# 🔥 PUBLIC EXPORTS (tests depend on these)
render_template = _render_template
get_db = _get_db
load_kiosk_activity_categories_for_shelter = (
    _load_kiosk_activity_categories_for_shelter
)
load_active_kiosk_activity_child_options_for_shelter = (
    _load_active_kiosk_activity_child_options_for_shelter
)
run_pass_retention_cleanup_for_shelter = (
    _run_pass_retention_cleanup_for_shelter
)


def _proxy(name):
    def _inner(*args, **kwargs):
        return globals()[name](*args, **kwargs)
    return _inner


def _load_route_parts():
    parts = {
        "home": import_module("routes.resident_portal_parts.home"),
        "chores": import_module("routes.resident_portal_parts.chores"),
        "daily_log": import_module("routes.resident_portal_parts.daily_log"),
        "budget": import_module("routes.resident_portal_parts.budget"),
    }

    # Inject dynamic dependencies
    for module in parts.values():
        module.render_template = _proxy("render_template")
        module.get_db = _proxy("get_db")
        module.load_kiosk_activity_categories_for_shelter = _proxy(
            "load_kiosk_activity_categories_for_shelter"
        )
        module.load_active_kiosk_activity_child_options_for_shelter = _proxy(
            "load_active_kiosk_activity_child_options_for_shelter"
        )
        module.run_pass_retention_cleanup_for_shelter = _proxy(
            "run_pass_retention_cleanup_for_shelter"
        )

    return parts


_IMPORTED_PARTS = _load_route_parts()

# 🔥 REQUIRED exports
home = _IMPORTED_PARTS["home"].home
resident_chores = _IMPORTED_PARTS["chores"].resident_chores
resident_daily_log = _IMPORTED_PARTS["daily_log"].resident_daily_log
budget = _IMPORTED_PARTS["budget"]

# 🔥 CRITICAL for tests
def _load_recent_pass_items(*args, **kwargs):
    return _IMPORTED_PARTS["home"]._load_recent_pass_items(*args, **kwargs)
