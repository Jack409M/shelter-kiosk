from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_fetchone

auth = Blueprint("auth", __name__)


@auth.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    from app import _ban_ip, _client_ip, get_all_shelters, init_db
    from core.rate_limit import is_rate_limited

    init_db()
    all_shelters = get_all_shelters()

    if request.method == "GET":
        return render_template("staff_login.html", all_shelters=all_shelters)

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()

    ip = _client_ip()
    normalized_username = username.lower() or "blank"

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
        if is_rate_limited(f"staff_login_fail_ban_ip:{ip}", limit=20, window_seconds=3600):
            _ban_ip(ip, 3600)

        log_action("auth", None, None, None, "login_failed", f"reason=bad_username ip={ip} username={normalized_username}")
        flash("Invalid login.", "error")
        return render_template("staff_login.html", all_shelters=all_shelters), 401

    staff_user_id = row["id"] if isinstance(row, dict) else row[0]
    is_active = bool(row["is_active"] if isinstance(row, dict) else row[4])
    pw_hash = row["password_hash"] if isinstance(row, dict) else row[2]

    if not is_active or not check_password_hash(pw_hash, password):
        if is_rate_limited(f"staff_login_fail_ban_ip:{ip}", limit=20, window_seconds=3600):
            _ban_ip(ip, 3600)

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


@auth.route("/staff")
@require_login
@require_shelter
def staff_home():
    return redirect(url_for("attendance.staff_attendance"))
