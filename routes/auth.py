from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_fetchone
from core.rate_limit import ban_ip, is_ip_banned, is_rate_limited

auth = Blueprint("auth", __name__)


@auth.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    from app import _client_ip, get_all_shelters, init_db

    init_db()
    all_shelters = get_all_shelters()

    if request.method == "GET":
        return render_template("staff_login.html", all_shelters=all_shelters)

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()

    ip = _client_ip()
    normalized_username = username.lower() or "blank"

    if is_ip_banned(ip):
        log_action("auth", None, None, None, "login_blocked_banned_ip", f"ip={ip} username={normalized_username}")
        flash("Too many login attempts. Please wait and try again later.", "error")
        return render_template("staff_login.html", all_shelters=all_shelters), 403

    if is_rate_limited(f"staff_login_ip:{ip}", limit=10, window_seconds=900):
        log_action("auth", None, None, None, "login_rate_limited_ip", f"ip={ip} username={normalized_username}")
        flash("Too many login attempts. Please wait and try again.", "error")
        return render_template("staff_login.html", all_shelters=all_shelters), 429

    if is_rate_limited(f"staff_login_user:{normalized_username}", limit=8, window_seconds=900):
        log_action("auth", None, None, None, "login_rate_limited_user", f"ip={ip} username={normalized_username}")
        flash("Too many login attempts for that account. Please wait and try again.", "error")
        return render_template("staff_login.html", all_shelters=all_shelters), 429

    row = db_fetchone(
        "SELECT * FROM staff_users WHERE username = %s"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM staff_users WHERE username = ?",
        (username,),
    )

    if not row:
        triggered_ban = is_rate_limited(f"staff_login_fail_ban_ip:{ip}", limit=20, window_seconds=3600)
        if triggered_ban:
            ban_ip(ip, 3600)
            log_action("auth", None, None, None, "login_ip_banned", f"reason=too_many_failed_logins ip={ip} username={normalized_username} seconds=3600")

        log_action("auth", None, None, None, "login_failed", f"reason=bad_username ip={ip} username={normalized_username}")
        flash("Invalid login.", "error")
        return render_template("staff_login.html", all_shelters=all_shelters), 401

    staff_user_id = row["id"] if isinstance(row, dict) else row[0]
    is_active = bool(row["is_active"] if isinstance(row, dict) else row[4])
    pw_hash = row["password_hash"] if isinstance(row, dict) else row[2]

    if not is_active or not check_password_hash(pw_hash, password):
        triggered_ban = is_rate_limited(f"staff_login_fail_ban_ip:{ip}", limit=20, window_seconds=3600)
        if triggered_ban:
            ban_ip(ip, 3600)
            log_action(
                "auth",
                None,
                None,
                staff_user_id,
                "login_ip_banned",
                f"reason=too_many_failed_logins ip={ip} username={normalized_username} seconds=3600",
            )

        log_action(
            "auth",
            None,
            None,
            staff_user_id,
            "login_failed",
            f"reason=bad_password_or_inactive ip={ip} username={normalized_username}",
        )
        flash("Invalid login.", "error")
        return render_template("staff_login.html", all_shelters=all_shelters), 401

    shelter = (request.form.get("shelter") or "").strip()
    if shelter not in all_shelters:
        log_action(
            "auth",
            None,
            None,
            staff_user_id,
            "login_failed",
            f"reason=invalid_shelter ip={ip} username={normalized_username} shelter={shelter}",
        )
        flash("Select a valid shelter.", "error")
        return render_template("staff_login.html", all_shelters=all_shelters), 400

    session.clear()
    session["staff_user_id"] = staff_user_id
    session["username"] = row["username"] if isinstance(row, dict) else row[1]
    session["role"] = row["role"] if isinstance(row, dict) else row[3]
    session["shelter"] = shelter
    session.permanent = True

    log_action(
        "auth",
        None,
        shelter,
        session["staff_user_id"],
        "login",
        f"Staff login: {session['username']} ip={ip}",
    )

    if session.get("role") == "admin":
        return redirect(url_for("admin.admin_dashboard"))

    return redirect(url_for("attendance.staff_attendance"))


@auth.route("/staff/logout")
@require_login
def staff_logout():
    staff_id = session.get("staff_user_id")
    log_action("auth", None, None, staff_id, "logout", f"Staff logout: {session.get('username')}")
    session.clear()
    return redirect(url_for("auth.staff_login"))


@auth.route("/staff/select-shelter", methods=["GET", "POST"])
@require_login
def staff_select_shelter():
    from app import get_all_shelters

    shelters = get_all_shelters()

    if request.method == "GET":
        return render_template("staff_select_shelter.html", shelters=shelters)

    shelter = (request.form.get("shelter") or "").strip()
    if shelter not in shelters:
        flash("Select a valid shelter.", "error")
        return redirect(url_for("auth.staff_select_shelter"))

    session["shelter"] = shelter

    nxt = (request.form.get("next") or "").strip()
    if nxt and nxt.startswith("/staff"):
        return redirect(nxt)

    return redirect(url_for("auth.staff_home"))


@auth.route("/staff/profile", methods=["GET", "POST"])
@require_login
@require_shelter
def staff_profile():
    from core.db import db_execute
    from werkzeug.security import generate_password_hash

    staff_id = session.get("staff_user_id")

    row = db_fetchone(
        "SELECT id, first_name, last_name, username, role, email, mobile_phone, is_active, created_at "
        "FROM staff_users WHERE id = %s"
        if g.get("db_kind") == "pg"
        else "SELECT id, first_name, last_name, username, role, email, mobile_phone, is_active, created_at "
             "FROM staff_users WHERE id = ?",
        (staff_id,),
    )

    if not row:
        flash("User record not found.", "error")
        return redirect(url_for("auth.staff_home"))

    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        email = (request.form.get("email") or "").strip()
        mobile_phone = (request.form.get("mobile_phone") or "").strip()
        password = (request.form.get("password") or "").strip()

        db_execute(
            "UPDATE staff_users SET first_name=%s, last_name=%s, email=%s, mobile_phone=%s WHERE id=%s"
            if g.get("db_kind") == "pg"
            else "UPDATE staff_users SET first_name=?, last_name=?, email=?, mobile_phone=? WHERE id=?",
            (first_name, last_name, email, mobile_phone, staff_id),
        )

        if password:
            db_execute(
                "UPDATE staff_users SET password_hash=%s WHERE id=%s"
                if g.get("db_kind") == "pg"
                else "UPDATE staff_users SET password_hash=? WHERE id=?",
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


@auth.route("/staff")
@require_login
@require_shelter
def staff_home():
    if (session.get("role") or "").strip() == "admin":
        return redirect(url_for("admin.admin_dashboard"))

    return redirect(url_for("attendance.staff_attendance"))
