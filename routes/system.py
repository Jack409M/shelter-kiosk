from __future__ import annotations

from flask import Blueprint, abort, current_app, g, redirect, render_template, url_for

from core.auth import require_login
from core.db import db_fetchone


system = Blueprint("system", __name__)


def _is_admin() -> bool:
    return session_role() == "admin"


def session_role() -> str:
    from flask import session
    return (session.get("role") or "").strip()


def _init_db():
    # Import inside the function so blueprint loading does not create a circular import.
    from app import init_db
    return init_db()


@system.post("/debug/csrf-post")
@require_login
def debug_csrf_post():
    if not current_app.config.get("ENABLE_DEBUG_ROUTES", False):
        abort(404)
    return "CSRF OK", 200


@system.route("/debug/db")
@require_login
def debug_db():
    if not current_app.config.get("ENABLE_DEBUG_ROUTES", False):
        abort(404)

    if not _is_admin():
        return redirect(url_for("auth.staff_home"))

    try:
        _init_db()
    except Exception:
        return {"ok": False, "error": "db init failed", "db_kind": g.get("db_kind")}, 500

    return {"ok": True, "db_kind": g.get("db_kind")}


@system.get("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.ico"), code=301)


@system.get("/health")
def health():
    return {"status": "ok"}, 200
