from __future__ import annotations

from functools import wraps

from flask import flash, redirect, request, session, url_for

from core.runtime import STAFF_ROLES, TRANSFER_ROLES


def _staff_home_redirect():
    return redirect(url_for("attendance.staff_attendance"))


# ------------------------------------------------------------
# Staff / admin access control
# ------------------------------------------------------------


def require_staff_or_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in STAFF_ROLES:
            flash("Staff only.", "error")
            return _staff_home_redirect()
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin only.", "error")
            return _staff_home_redirect()
        return fn(*args, **kwargs)

    return wrapper


# ------------------------------------------------------------
# Resident access control
# ------------------------------------------------------------


def require_resident(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        required_values = (
            session.get("resident_id"),
            session.get("resident_identifier"),
            session.get("resident_first"),
            session.get("resident_last"),
            session.get("resident_shelter"),
        )
        if any(not value for value in required_values):
            session.clear()
            return redirect(
                url_for(
                    "resident_requests.resident_signin",
                    next=request.path,
                )
            )
        return fn(*args, **kwargs)

    return wrapper


# ------------------------------------------------------------
# Transfer access
# ------------------------------------------------------------


def require_transfer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in TRANSFER_ROLES:
            flash("Admin or case manager only.", "error")
            return _staff_home_redirect()
        return fn(*args, **kwargs)

    return wrapper


# ------------------------------------------------------------
# Resident creation permission
# ------------------------------------------------------------


def require_resident_create(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in {"admin", "case_manager"}:
            flash("Admin or case manager only.", "error")
            return _staff_home_redirect()
        return fn(*args, **kwargs)

    return wrapper
