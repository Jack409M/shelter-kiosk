from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.db import get_db
from core.pass_retention import run_pass_retention_cleanup_for_shelter

resident_portal = Blueprint("resident_portal", __name__)


def _clear_resident_session() -> None:
    session.clear()


def _resident_signin_redirect():
    return redirect(url_for("resident_requests.resident_signin", next=request.path))


def _load_recent_pass_items(resident_id: int | None, shelter: str) -> list[dict]:
    return []


@resident_portal.route("/resident/home")
@require_resident
def home():
    try:
        resident_id_raw = session.get("resident_id")
        resident_id = int(resident_id_raw) if resident_id_raw not in (None, "") else None
        shelter = str(session.get("resident_shelter") or "").strip()

        get_db()

        if shelter:
            run_pass_retention_cleanup_for_shelter(shelter)

        recent_items = _load_recent_pass_items(resident_id, shelter)

        return render_template(
            "resident_home.html",
            recent_items=recent_items,
        )
    except Exception:
        _clear_resident_session()
        return _resident_signin_redirect()


@resident_portal.route("/resident/chores")
@require_resident
def resident_chores():
    try:
        shelter = str(session.get("resident_shelter") or "").strip()

        get_db()

        if shelter:
            run_pass_retention_cleanup_for_shelter(shelter)

        return render_template("resident_chores.html")
    except Exception:
        _clear_resident_session()
        return _resident_signin_redirect()
