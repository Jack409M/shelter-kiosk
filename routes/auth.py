from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.db import db_fetchone
from core.helpers import utcnow_iso

auth = Blueprint("auth", __name__)


@auth.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    from app import check_staff_password

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()

        user = db_fetchone(
            "SELECT * FROM staff_users WHERE username = %s"
            if session.get("db_kind") == "pg"
            else "SELECT * FROM staff_users WHERE username = ?",
            (username,),
        )

        if not user:
            flash("Invalid credentials.", "error")
            return redirect(url_for("auth.staff_login"))

        if not check_staff_password(user, password):
            flash("Invalid credentials.", "error")
            return redirect(url_for("auth.staff_login"))

        session["staff_user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]

        flash("Logged in.", "ok")
        return redirect(url_for("staff_home"))

    return render_template("staff_login.html")


@auth.route("/staff/logout")
def staff_logout():
    session.clear()
    flash("Logged out.", "ok")
    return redirect(url_for("auth.staff_login"))


@auth.route("/staff")
def staff_home():
    if not session.get("staff_user_id"):
        return redirect(url_for("auth.staff_login"))

    return render_template("staff_home.html")


@auth.route("/staff/select-shelter", methods=["GET", "POST"])
def staff_select_shelter():
    from app import SHELTERS

    if request.method == "POST":
        shelter = (request.form.get("shelter") or "").strip()

        if shelter not in SHELTERS:
            flash("Invalid shelter.", "error")
            return redirect(url_for("auth.staff_select_shelter"))

        session["shelter"] = shelter
        return redirect(url_for("auth.staff_home"))

    return render_template("staff_select_shelter.html", shelters=SHELTERS)


@auth.route("/resident")
def resident_signin():
    return render_template("resident_signin.html")


@auth.route("/resident/login", methods=["POST"])
def resident_login_alias():
    return redirect(url_for("resident_signin"))


@auth.route("/resident/login/")
def resident_login_alias_slash():
    return redirect(url_for("resident_signin"))


@auth.route("/resident/logout")
def resident_logout():
    session.clear()
    flash("Logged out.", "ok")
    return redirect(url_for("resident_signin"))
