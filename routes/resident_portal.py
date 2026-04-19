from __future__ import annotations

from flask import Blueprint

resident_portal = Blueprint("resident_portal", __name__)

# Register resident portal route parts.
from routes.resident_portal_parts import home  # noqa: E402,F401
from routes.resident_portal_parts import chores  # noqa: E402,F401
from routes.resident_portal_parts import daily_log  # noqa: E402,F401
from routes.resident_portal_parts import budget  # noqa: E402,F401
