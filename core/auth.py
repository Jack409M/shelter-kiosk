from __future__ import annotations

from functools import wraps

from flask import flash, session, redirect, url_for

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
        if "shelter" not in session:
            return redirect(url_for("staff_select_shelter"))
        return fn(*args, **kwargs)

    return wrapper
    
