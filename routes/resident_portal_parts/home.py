from __future__ import annotations

from flask import current_app

import routes.resident_portal as portal
from core.access import require_resident
from core.resident_portal_service import get_today_chores
from routes.resident_portal import resident_portal
from routes.resident_portal_parts.helpers import (
    _clear_resident_session,
    _load_active_pass_item,
    _load_recent_notification_items,
    _load_recent_transport_items,
    _load_resident_program_level,
    _prepare_resident_request_context,
    _resident_signin_redirect,
)


@resident_portal.route("/resident/home")
@require_resident
def home():
    resident_id = None
    shelter = ""

    try:
        resident_id, shelter, resident_identifier = _prepare_resident_request_context()

        portal.get_db()
        portal.run_pass_retention_cleanup_for_shelter(shelter)

        resident_level = _load_resident_program_level(resident_id)

        pass_items = portal._load_recent_pass_items(resident_id, shelter)

        active_pass = _load_active_pass_item(resident_id, shelter)
        notification_items = _load_recent_notification_items(resident_id, shelter)
        transport_items = _load_recent_transport_items(resident_identifier, shelter)
        chores = get_today_chores(resident_id) if resident_id is not None else []

        return portal.render_template(
            "resident_home.html",
            recent_items=pass_items,
            pass_items=pass_items,
            active_pass=active_pass,
            notification_items=notification_items,
            transport_items=transport_items,
            chores=chores,
            resident_level=resident_level,
        )

    except Exception as exc:
        current_app.logger.exception(
            "resident_portal_home_failed resident_id=%s shelter=%s exception_type=%s",
            resident_id if resident_id is not None else "unknown",
            shelter or "unknown",
            type(exc).__name__,
        )
        _clear_resident_session()
        return _resident_signin_redirect()
