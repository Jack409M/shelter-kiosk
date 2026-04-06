from __future__ import annotations

from flask import Blueprint

from .rent_tracking_parts.views import register_routes


rent_tracking = Blueprint(
    "rent_tracking",
    __name__,
    url_prefix="/staff/rent",
)

register_routes(rent_tracking)
