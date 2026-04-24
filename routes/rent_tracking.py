from __future__ import annotations

from flask import Blueprint

from .rent_tracking_parts.payment_station_views import register_payment_station_routes
from .rent_tracking_parts.rent_roll import register_rent_roll_routes
from .rent_tracking_parts.resident_account import register_resident_account_routes
from .rent_tracking_parts.snapshot import build_rent_stability_snapshot
from .rent_tracking_parts.views import register_routes

rent_tracking = Blueprint(
    "rent_tracking",
    __name__,
    url_prefix="/staff/rent",
)

register_rent_roll_routes(rent_tracking)
register_routes(rent_tracking)
register_resident_account_routes(rent_tracking)
register_payment_station_routes(rent_tracking)

__all__ = [
    "rent_tracking",
    "build_rent_stability_snapshot",
]
