from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchall
from core.runtime import init_db
from routes.admin_parts.helpers import (
    current_role as _current_role,
    require_admin_or_shelter_director_role as _require_admin_or_shelter_director,
)

staff_email_admin = Blueprint("staff_email_admin", __name__)


def _ph() -> str:
    from flask import current_app

    return "%s" if current_app.config.get("DATABASE_URL") else "?"


def _normalize_email(value: str | None) -> str | None:
    email = (value or "").strip().lower()
    return email or None


def _can_manage_role(role: str) -> bool:
    current_role = _current_role()
    if current_role == "admin":
        return True
    if current_role == "shelter_director":
        return role in {"staff", "case_manager", "ra"}
    return False


@staff_email_admin.route("/staff/admin/staff-emails", methods=["GET", "POST"])
def staff_email_management():
    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    if request.method == "POST":
        user_id_raw = (request.form.get("user_id") or "").strip()
        email = _normalize_email(request.form.get("email"))

        try:
            user_id = int(user_id_raw)
        except (TypeError, ValueError):
            flash("Invalid user.", "error")
            return redirect(url_for("staff_email_admin.staff_email_management"))

        rows = db_fetchall(
            f"SELECT id, username, role FROM staff_users WHERE id = {_ph()}",
            (user_id,),
        )
        if not rows:
            flash("User not found.", "error")
            return redirect(url_for("staff_email_admin.staff_email_management"))

        target = rows[0]
        target_role = (target["role"] or "").strip()
        target_username = (target["username"] or "").strip()

        if not _can_manage_role(target_role):
            flash("You are not allowed to manage that user.", "error")
            return redirect(url_for("staff_email_admin.staff_email_management"))

        db_execute(
            f"UPDATE staff_users SET email = {_ph()} WHERE id = {_ph()}",
            (email, user_id),
        )

        log_action(
            "staff_user",
            user_id,
            None,
            session.get("staff_user_id"),
            "staff_email_update",
            {"username": target_username, "email_present": bool(email)},
        )

        flash("Staff email updated.", "ok")
        return redirect(url_for("staff_email_admin.staff_email_management"))

    where_sql = ""
    params: tuple = ()
    if _current_role() != "admin":
        where_sql = "WHERE role IN ('staff', 'case_manager', 'ra')"

    users = db_fetchall(
        f"""
        SELECT id, first_name, last_name, username, role, is_active, email
        FROM staff_users
        {where_sql}
        ORDER BY last_name ASC NULLS LAST, first_name ASC NULLS LAST, username ASC
        """,
        params,
    )

    return render_template("staff_email_management.html", users=users)
