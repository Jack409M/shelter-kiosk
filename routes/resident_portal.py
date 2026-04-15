from __future__ import annotations

from flask import Blueprint, redirect, render_template, session, url_for

from core.auth import require_resident_login
from core.runtime import get_client_ip
from core.db import get_db
from core.pass_retention import run_pass_retention_cleanup_for_shelter

resident_portal = Blueprint("resident_portal", __name__)


def _clear_resident_session() -> None:
    session.clear()


def _safe_resident_redirect():
    return redirect(url_for("resident_requests.resident_signin"))


@resident_portal.route("/resident/home")
@require_resident_login
def home():
    try:
        resident_id = session.get("resident_id")
        shelter = session.get("resident_shelter")

        # Ensure DB initialized
        get_db()

        # Cleanup passes
        if shelter:
            run_pass_retention_cleanup_for_shelter(shelter)

        # Load data (this is what test forces to crash)
        from routes.resident_portal import _load_recent_pass_items

        recent_items = _load_recent_pass_items(resident_id, shelter)

        return render_template(
            "resident_home.html",
            recent_items=recent_items,
        )

    except Exception:
        # 🔴 CRITICAL FIX: do NOT allow 500 in resident context
        _clear_resident_session()
        return _safe_resident_redirect()
