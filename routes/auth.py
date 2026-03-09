from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_fetchone


auth = Blueprint("auth", __name__)


@auth.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    from app import _client_ip, get_all_shelters, init_db
    from core.rate_limit import is_rate_limited

    init_db()
    all_shelters = get_all_shelters()

    if request.method == "GET":
        return render_template("staff_login.html", all_shelters=all_shelters)

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()

    ip = _client_ip()
    normalized_username = username.lower()

    if is_rate_limited(f"staff_login_ip:{ip}", 10, 60) or is_rate_limited(
        f"staff_login_user:{normalized_username}", 20, 3600
    ):
        flash("Too many login attempts. Please wait and try again.", "error")
        return render_template("staff_login.html", all_shelters=all_shelters), 429

    row = db_fetchone(
        "SELECT * FROM staff_users WHERE username = %s"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM staff_users WHERE username = ?",
        (username,),
    )

    if not row:
        flash("Invalid login.", "error")
        return render_template("staff_login.html", all_shelters=all_shelters), 401

    is_active = bool(row["is_active"] if isinstance(row, dict) else row[4])
    pw_hash = row["password_hash"] if isinstance(row, dict) else row[2]

    if not is_active or not check_password_hash(pw_hash, password):
        flash("Invalid login.", "error")
        return render_template("staff_login.html", all_shelters=all_shelters), 401

    shelter = (request.form.get("shelter") or "").strip()
    if shelter not in all_shelters:
        flash("Select a valid shelter.", "error")
        return render_template("staff_login.html", all_shelters=all_shelters), 400

    session.clear()
    session["staff_user_id"] = row["id"] if isinstance(row, dict) else row[0]
    session["username"] = row["username"] if isinstance(row, dict) else row[1]
    session["role"] = row["role"] if isinstance(row, dict) else row[3]
    session["shelter"] = shelter
    session.permanent = True

    log_action("auth", None, None, session["staff_user_id"], "login", f"Staff login: {session['username']}")
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
