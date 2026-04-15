from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.rate_limit import (
    ban_ip,
    get_key_lock_seconds_remaining,
    get_progressive_lock_seconds,
    is_ip_banned,
    is_key_locked,
    is_rate_limited,
    lock_key,
)
from core.runtime import get_all_shelters, get_client_ip

auth = Blueprint("auth", __name__)


def _safe_log_value(value: str | None, max_length: int = 80) -> str:
    text = (value or "").strip()
    if not text:
        return "blank"
    text = "".join(ch if 32 <= ord(ch) <= 126 else "?" for ch in text)
    return text[:max_length]


def _db_sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _load_all_shelters() -> tuple[list[str], list[str], set[str]]:
    all_shelters_raw = get_all_shelters()
    all_shelters: list[str] = []
    all_shelters_lower: list[str] = []

    for shelter_name in all_shelters_raw:
        cleaned = (shelter_name or "").strip()
        if not cleaned:
            continue
        all_shelters.append(cleaned)
        all_shelters_lower.append(cleaned.lower())

    return all_shelters, all_shelters_lower, set(all_shelters_lower)


def _render_staff_login(all_shelters: list[str], status_code: int = 200):
    return render_template("staff_login.html", all_shelters=all_shelters), status_code


def _normalized_username_from_form() -> tuple[str, str]:
    username = (request.form.get("username") or "").strip()
    normalized_username = username.lower() or "blank"
    return username, normalized_username


def _username_lock_key(normalized_username: str) -> str:
    return f"staff_login_username_lock:{normalized_username}"


def _record_failed_login_attempt(
    *,
    ip: str,
    normalized_username: str,
    safe_username: str,
    staff_user_id: int | None,
) -> None:
    username_lock_key = _username_lock_key(normalized_username)

    triggered_username_lock = is_rate_limited(
        f"staff_login_fail_username_lock:{normalized_username}",
        limit=8,
        window_seconds=900,
    )
    if triggered_username_lock:
        lock_seconds = get_progressive_lock_seconds(username_lock_key)
        lock_key(username_lock_key, lock_seconds)
        log_action(
            "auth",
            None,
            None,
            staff_user_id,
            "login_username_locked",
            f"reason=too_many_failed_logins ip={ip} username={safe_username} seconds={lock_seconds}",
        )

    triggered_ban = is_rate_limited(
        f"staff_login_fail_ban_ip:{ip}",
        limit=20,
        window_seconds=3600,
    )
    if triggered_ban:
        ban_ip(ip, 3600)
        log_action(
            "auth",
            None,
            None,
            staff_user_id,
            "login_ip_banned",
            f"reason=too_many_failed_logins ip={ip} username={safe_username} seconds=3600",
        )


def _load_staff_user_by_username(normalized_username: str):
    return db_fetchone(
        _db_sql(
            "SELECT * FROM staff_users WHERE LOWER(username) = %s",
            "SELECT * FROM staff_users WHERE LOWER(username) = ?",
        ),
        (normalized_username,),
    )


def _load_allowed_shelters_for_user(
    *,
    staff_user_id: int,
    staff_role: str,
    all_shelters_lower: list[str],
    all_shelters_lower_set: set[str],
) -> list[str]:
    if staff_role in {"admin", "shelter_director"}:
        return list(all_shelters_lower)

    shelter_rows = db_fetchall(
        _db_sql(
            "SELECT shelter FROM staff_shelter_assignments WHERE staff_user_id = %s ORDER BY shelter",
            "SELECT shelter FROM staff_shelter_assignments WHERE staff_user_id = ? ORDER BY shelter",
        ),
        (staff_user_id,),
    )

    allowed_shelters: list[str] = []
    seen: set[str] = set()

    for shelter_row in shelter_rows:
        shelter_name = shelter_row["shelter"] if isinstance(shelter_row, dict) else shelter_row[0]
        shelter_name = (shelter_name or "").strip().lower()

        if shelter_name and shelter_name in all_shelters_lower_set and shelter_name not in seen:
            allowed_shelters.append(shelter_name)
            seen.add(shelter_name)

    return allowed_shelters


def _set_staff_session(
    *,
    staff_user_id: int,
    staff_username: str,
    staff_role: str,
    shelter: str,
    allowed_shelters: list[str],
) -> None:
    session["staff_user_id"] = staff_user_id
    session["username"] = staff_username
    session["role"] = staff_role
    session["shelter"] = shelter
    session["allowed_shelters"] = allowed_shelters
    session.permanent = True


@auth.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    all_shelters, all_shelters_lower, all_shelters_lower_set = _load_all_shelters()

    if request.method == "GET":
        return render_template("staff_login.html", all_shelters=all_shelters)

    _, normalized_username = _normalized_username_from_form()
    password = (request.form.get("password") or "").strip()

    ip = get_client_ip()
    safe_username = _safe_log_value(normalized_username)
    username_lock_key = _username_lock_key(normalized_username)

    if is_ip_banned(ip):
        log_action(
            "auth", None, None, None, "login_blocked_banned_ip", f"ip={ip} username={safe_username}"
        )
        flash("Too many login attempts. Please wait and try again later.", "error")
        return _render_staff_login(all_shelters, 403)

    if is_key_locked(username_lock_key):
        seconds_remaining = get_key_lock_seconds_remaining(username_lock_key)
        log_action(
            "auth",
            None,
            None,
            None,
            "login_blocked_locked_username",
            f"ip={ip} username={safe_username} seconds_remaining={seconds_remaining}",
        )
        flash("That username is temporarily locked. Please wait and try again.", "error")
        return _render_staff_login(all_shelters, 429)

    if is_rate_limited(f"staff_login_ip:{ip}", limit=10, window_seconds=900):
        log_action(
            "auth", None, None, None, "login_rate_limited_ip", f"ip={ip} username={safe_username}"
        )
        flash("Too many login attempts. Please wait and try again.", "error")
        return _render_staff_login(all_shelters, 429)

    if is_rate_limited(f"staff_login_user:{normalized_username}", limit=8, window_seconds=900):
        log_action(
            "auth", None, None, None, "login_rate_limited_user", f"ip={ip} username={safe_username}"
        )
        flash("Too many login attempts for that account. Please wait and try again.", "error")
        return _render_staff_login(all_shelters, 429)

    row = _load_staff_user_by_username(normalized_username)

    if not row:
        _record_failed_login_attempt(
            ip=ip,
            normalized_username=normalized_username,
            safe_username=safe_username,
            staff_user_id=None,
        )
        log_action(
            "auth",
            None,
            None,
            None,
            "login_failed",
            f"reason=bad_username ip={ip} username={safe_username}",
        )
        flash("Invalid login.", "error")
        return _render_staff_login(all_shelters, 401)

    staff_user_id = row["id"] if isinstance(row, dict) else row[0]
    staff_username = row["username"] if isinstance(row, dict) else row[1]
    pw_hash = row["password_hash"] if isinstance(row, dict) else row[2]
    staff_role = row["role"] if isinstance(row, dict) else row[3]
    is_active = bool(row["is_active"] if isinstance(row, dict) else row[4])

    if not is_active or not check_password_hash(pw_hash, password):
        _record_failed_login_attempt(
            ip=ip,
            normalized_username=normalized_username,
            safe_username=safe_username,
            staff_user_id=staff_user_id,
        )
        log_action(
            "auth",
            None,
            None,
            staff_user_id,
            "login_failed",
            f"reason=bad_password_or_inactive ip={ip} username={safe_username}",
        )
        flash("Invalid login.", "error")
        return _render_staff_login(all_shelters, 401)

    allowed_shelters = _load_allowed_shelters_for_user(
        staff_user_id=staff_user_id,
        staff_role=staff_role,
        all_shelters_lower=all_shelters_lower,
        all_shelters_lower_set=all_shelters_lower_set,
    )

    if not allowed_shelters:
        log_action(
            "auth",
            None,
            None,
            staff_user_id,
            "login_failed",
            f"reason=no_assigned_shelters ip={ip} username={safe_username}",
        )
        flash(
            "Your account does not have any shelter access assigned. Please contact an administrator.",
            "error",
        )
        return _render_staff_login(all_shelters, 403)

    shelter = (request.form.get("shelter") or "").strip().lower()
    if shelter not in allowed_shelters:
        log_action(
            "auth",
            None,
            None,
            staff_user_id,
            "login_failed",
            f"reason=invalid_shelter_for_user ip={ip} username={safe_username} shelter={shelter}",
        )
        flash("You do not have access to that shelter.", "error")
        return _render_staff_login(all_shelters, 403)

    session.clear()
    _set_staff_session(
        staff_user_id=staff_user_id,
        staff_username=staff_username,
        staff_role=staff_role,
        shelter=shelter,
        allowed_shelters=allowed_shelters,
    )

    log_action(
        "auth",
        None,
        shelter,
        session["staff_user_id"],
        "login",
        f"Staff login: {_safe_log_value(session['username'])} ip={ip}",
    )

    if session.get("role") == "admin":
        return redirect(url_for("admin.admin_dashboard"))

    return redirect(url_for("attendance.staff_attendance"))


@auth.route("/staff/logout")
@require_login
def staff_logout():
    staff_id = session.get("staff_user_id")
    log_action(
        "auth",
        None,
        None,
        staff_id,
        "logout",
        f"Staff logout: {_safe_log_value(session.get('username'))}",
    )
    session.clear()
    return redirect(url_for("auth.staff_login"))


@auth.route("/staff/select-shelter", methods=["GET", "POST"])
@require_login
def staff_select_shelter():
    all_shelters, all_shelters_lower, _ = _load_all_shelters()
    allowed_shelters = session.get("allowed_shelters") or all_shelters_lower
    allowed_shelters_set = {str(shelter).strip().lower() for shelter in allowed_shelters if shelter}

    shelters = [
        original_shelter
        for original_shelter, lower_shelter in zip(all_shelters, all_shelters_lower)
        if lower_shelter in allowed_shelters_set
    ]

    if request.method == "GET":
        return render_template("staff_select_shelter.html", shelters=shelters)

    shelter = (request.form.get("shelter") or "").strip().lower()
    if shelter not in allowed_shelters_set:
        flash("Select a valid shelter.", "error")
        return redirect(url_for("auth.staff_select_shelter"))

    session["shelter"] = shelter

    nxt = (request.form.get("next") or "").strip()
    if nxt and nxt.startswith("/staff"):
        return redirect(nxt)

    return redirect(url_for("attendance.staff_attendance"))


@auth.route("/staff/profile", methods=["GET", "POST"])
@require_login
@require_shelter
def staff_profile():
    staff_id = session.get("staff_user_id")

    row = db_fetchone(
        _db_sql(
            (
                "SELECT id, first_name, last_name, username, role, email, mobile_phone, "
                "is_active, created_at FROM staff_users WHERE id = %s"
            ),
            (
                "SELECT id, first_name, last_name, username, role, email, mobile_phone, "
                "is_active, created_at FROM staff_users WHERE id = ?"
            ),
        ),
        (staff_id,),
    )

    if not row:
        flash("User record not found.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        email = (request.form.get("email") or "").strip()
        mobile_phone = (request.form.get("mobile_phone") or "").strip()
        password = (request.form.get("password") or "").strip()

        db_execute(
            _db_sql(
                "UPDATE staff_users SET first_name=%s, last_name=%s, email=%s, mobile_phone=%s WHERE id=%s",
                "UPDATE staff_users SET first_name=?, last_name=?, email=?, mobile_phone=? WHERE id=?",
            ),
            (first_name, last_name, email, mobile_phone, staff_id),
        )

        if password:
            db_execute(
                _db_sql(
                    "UPDATE staff_users SET password_hash=%s WHERE id=%s",
                    "UPDATE staff_users SET password_hash=? WHERE id=?",
                ),
                (generate_password_hash(password), staff_id),
            )

        log_action(
            "staff_user",
            staff_id,
            session.get("shelter"),
            staff_id,
            "profile_update",
            "User updated own profile",
        )

        flash("Profile updated.", "ok")
        return redirect(url_for("auth.staff_profile"))

    return render_template("staff_profile.html", user=row)
