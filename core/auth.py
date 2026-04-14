from __future__ import annotations

from functools import wraps

from flask import current_app, flash, redirect, session, url_for

from core.db import db_fetchone

REQUEST_MANAGER_ROLES = {
    "admin",
    "shelter_director",
    "case_manager",
}

PASS_STATUS_ROLES = {
    "admin",
    "shelter_director",
    "case_manager",
    "ra",
    "staff",
}


def _current_role() -> str:
    return (session.get("role") or "").strip()


def _has_staff_session() -> bool:
    return "staff_user_id" in session


def _redirect_login():
    return redirect(url_for("auth.staff_login"))


def _redirect_staff_home():
    return redirect(url_for("attendance.staff_attendance"))


def _clear_invalid_session_and_redirect():
    session.clear()
    flash("Your session became invalid. Please log in again.", "error")
    return _redirect_login()


def _admin_only_mode_enabled() -> bool:
    try:
        row = db_fetchone(
            "SELECT admin_login_only_mode FROM security_settings ORDER BY id ASC LIMIT 1"
        )
    except Exception:
        current_app.logger.exception("Failed to read admin_login_only_mode from security_settings.")
        return False

    if not row:
        return False

    if isinstance(row, dict):
        return bool(row.get("admin_login_only_mode"))

    return bool(row[0])


def _enforce_admin_only_mode():
    if not _admin_only_mode_enabled():
        return None

    if _current_role() == "admin":
        return None

    session.clear()
    flash("System is currently restricted to administrators only.", "error")
    return _redirect_login()


def _ensure_staff_session():
    if not _has_staff_session():
        return _redirect_login()

    if not _current_role():
        return _clear_invalid_session_and_redirect()

    return _enforce_admin_only_mode()


def can_manage_requests() -> bool:
    return _current_role() in REQUEST_MANAGER_ROLES


def can_view_pass_status() -> bool:
    return _current_role() in PASS_STATUS_ROLES


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        response = _ensure_staff_session()
        if response is not None:
            return response

        return fn(*args, **kwargs)

    return wrapper


def require_shelter(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        shelter = (session.get("shelter") or "").strip()
        allowed_shelters = session.get("allowed_shelters") or []

        if not shelter:
            return redirect(url_for("auth.staff_select_shelter"))

        if allowed_shelters and shelter not in allowed_shelters:
            return _clear_invalid_session_and_redirect()

        return fn(*args, **kwargs)

    return wrapper


def require_roles(*allowed_roles):
    normalized_allowed_roles = {
        str(role).strip()
        for role in allowed_roles
        if str(role).strip()
    }

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            response = _ensure_staff_session()
            if response is not None:
                return response

            if _current_role() not in normalized_allowed_roles:
                flash("You do not have permission to access that page.", "error")
                return _redirect_staff_home()

            return fn(*args, **kwargs)

        return wrapper

    return decorator
