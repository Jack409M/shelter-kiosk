from __future__ import annotations

from functools import wraps

from flask import flash, redirect, request, session, url_for

from core.runtime import STAFF_ROLES, TRANSFER_ROLES


# ------------------------------------------------------------
# Staff / admin access control
# ------------------------------------------------------------

def require_staff_or_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in STAFF_ROLES:
            flash("Staff only.", "error")
            return redirect(url_for("auth.staff_home"))
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin only.", "error")
            return redirect(url_for("auth.staff_home"))
        return fn(*args, **kwargs)

    return wrapper


# ------------------------------------------------------------
# Resident access control
# ------------------------------------------------------------

def require_resident(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "resident_id" not in session:
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
            return redirect(url_for("auth.staff_home"))
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
            return redirect(url_for("auth.staff_home"))
        return fn(*args, **kwargs)

    return wrapper
