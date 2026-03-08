from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, url_for, g

from core.auth import require_login
from app import ENABLE_DEBUG_ROUTES, init_db, require_admin


system = Blueprint("system", __name__)


@system.post("/debug/csrf-post")
@require_login
def debug_csrf_post():
    if not ENABLE_DEBUG_ROUTES:
        abort(404)
    return "CSRF OK", 200


@system.route("/debug/db")
@require_login
@require_admin
def debug_db():
    if not ENABLE_DEBUG_ROUTES:
        abort(404)

    try:
        init_db()
    except Exception:
        return {"ok": False, "error": "db init failed", "db_kind": g.get("db_kind")}, 500

    return {"ok": True, "db_kind": g.get("db_kind")}


@system.get("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.ico"), code=301)


@system.get("/health")
def health():
    return {"status": "ok"}, 200
