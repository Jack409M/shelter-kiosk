from __future__ import annotations

from flask import abort, current_app, g, redirect, session, url_for, Blueprint

from core.auth import require_login


system = Blueprint("system", __name__)


def session_role() -> str:
    """
    Return the current user's role from session storage.
    Kept as a tiny helper so role checks stay readable.
    """
    return (session.get("role") or "").strip()


def _is_admin() -> bool:
    """
    True only when the current session belongs to an admin user.
    """
    return session_role() == "admin"


def _init_db() -> None:
    """
    Run the configured database initializer without importing app directly.

    The app stores the callable in:
        app.config["INIT_DB_FUNC"]

    This avoids circular imports during blueprint loading.
    """
    init_func = current_app.config.get("INIT_DB_FUNC")
    if callable(init_func):
        init_func()
        return
    raise RuntimeError("INIT_DB_FUNC is not configured")


@system.post("/debug/csrf-post")
@require_login
def debug_csrf_post():
    """
    Simple POST endpoint used to verify CSRF protection behavior.
    Only available when debug routes are enabled.
    """
    if not current_app.config.get("ENABLE_DEBUG_ROUTES", False):
        abort(404)

    return "CSRF OK", 200


@system.route("/debug/db")
@require_login
def debug_db():
    """
    Minimal database health/debug endpoint.

    Restricted to admins and only available when debug routes are enabled.
    Attempts to initialize the database layer and returns the detected db kind.
    """
    if not current_app.config.get("ENABLE_DEBUG_ROUTES", False):
        abort(404)

    if not _is_admin():
        return redirect(url_for("auth.staff_home"))

    try:
        _init_db()
    except Exception:
        return {"ok": False, "error": "db init failed", "db_kind": g.get("db_kind")}, 500

    return {"ok": True, "db_kind": g.get("db_kind")}, 200


@system.get("/favicon.ico")
def favicon():
    """
    Redirect browsers to the static favicon file.
    """
    return redirect(url_for("static", filename="favicon.ico"), code=301)


@system.get("/health")
def health():
    """
    Lightweight health endpoint for uptime checks and platform probes.
    """
    return {"status": "ok"}, 200


@system.get("/_routes")
def list_routes():
    """
    Disable public route listing in production.
    """
    abort(404)
