from __future__ import annotations

from functools import wraps

from flask import flash, redirect, session, url_for

from core.db import db_fetchone


def _admin_only_mode_enabled() -> bool:
    try:
        row = db_fetchone(
            "SELECT admin_login_only_mode FROM security_settings ORDER BY id ASC LIMIT 1"
        )
        if not row:
            return False
        return bool(row["admin_login_only_mode"] if isinstance(row, dict) else row[0])
    except Exception:
        return False


def _current_role() -> str:
    return (session.get("role") or "").strip()


def _has_staff_session() -> bool:
    return "staff_user_id" in session


def _redirect_login():
    return redirect(url_for("auth.staff_login"))


def _enforce_admin_only_mode():
    role = _current_role()

    if _admin_only_mode_enabled() and role != "admin":
        session.clear()
        flash("System is currently restricted to administrators only.", "error")
        return _redirect_login()

    return None


def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _has_staff_session():
            return _redirect_login()

        resp = _enforce_admin_only_mode()
        if resp is not None:
            return resp

        return f(*args, **kwargs)

    return wrapper


def require_shelter(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        shelter = (session.get("shelter") or "").strip()
        allowed_shelters = session.get("allowed_shelters") or []

        if not shelter:
            return redirect(url_for("auth.staff_select_shelter"))

        if allowed_shelters and shelter not in allowed_shelters:
            session.clear()
            flash("Your session became invalid. Please log in again.", "error")
            return _redirect_login()

        return fn(*args, **kwargs)

    return wrapper


def require_roles(*allowed_roles):
    normalized_allowed_roles = {str(role).strip() for role in allowed_roles if str(role).strip()}

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not _has_staff_session():
                return _redirect_login()

            resp = _enforce_admin_only_mode()
            if resp is not None:
                return resp

            role = _current_role()
            if role not in normalized_allowed_roles:
                flash("You do not have permission to access that page.", "error")
                return redirect(url_for("attendance.staff_attendance"))

            return fn(*args, **kwargs)

        return wrapper

    return decorator
