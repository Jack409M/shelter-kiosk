from __future__ import annotations

from functools import wraps

from flask import flash, redirect, request, session, url_for

from core.runtime import STAFF_ROLES, TRANSFER_ROLES


def _staff_home_redirect():
    return redirect(url_for("attendance.staff_attendance"))


def _clean_session_text(key: str) -> str:
    return str(session.get(key) or "").strip()


def _session_int(key: str) -> int | None:
    raw_value = session.get(key)
    if raw_value in (None, ""):
        return None

    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _clear_session_and_redirect_to_resident_signin():
    session.clear()
    return redirect(
        url_for(
            "resident_requests.resident_signin",
            next=request.path,
        )
    )


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
        resident_id = _session_int("resident_id")
        resident_identifier = _clean_session_text("resident_identifier")
        resident_first = _clean_session_text("resident_first")
        resident_last = _clean_session_text("resident_last")
        resident_shelter = _clean_session_text("resident_shelter")

        if (
            resident_id is None
            or not resident_identifier
            or not resident_first
            or not resident_last
            or not resident_shelter
        ):
            return _clear_session_and_redirect_to_resident_signin()

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
