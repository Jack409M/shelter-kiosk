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


def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "staff_user_id" not in session:
            return redirect(url_for("auth.staff_login"))

        if _admin_only_mode_enabled() and (session.get("role") or "").strip() != "admin":
            session.clear()
            flash("System is currently restricted to administrators only.", "error")
            return redirect(url_for("auth.staff_login"))

        return f(*args, **kwargs)

    return wrapper


def require_shelter(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        shelter = session.get("shelter")
        allowed_shelters = session.get("allowed_shelters")

        if not shelter:
            return redirect(url_for("auth.staff_select_shelter"))

        if allowed_shelters and shelter not in allowed_shelters:
            session.clear()
            flash("Your session became invalid. Please log in again.", "error")
            return redirect(url_for("auth.staff_login"))

        return fn(*args, **kwargs)

    return wrapper


def require_roles(*allowed_roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            role = (session.get("role") or "").strip()

            if "staff_user_id" not in session:
                return redirect(url_for("auth.staff_login"))

            if _admin_only_mode_enabled() and role != "admin":
                session.clear()
                flash("System is currently restricted to administrators only.", "error")
                return redirect(url_for("auth.staff_login"))

            if role not in allowed_roles:
                flash("You do not have permission to access that page.", "error")
                return redirect(url_for("staff_portal.staff_home"))

            return fn(*args, **kwargs)

        return wrapper

    return decorator
