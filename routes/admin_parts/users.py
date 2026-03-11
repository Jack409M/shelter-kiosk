from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchall
from core.helpers import fmt_dt
from routes.admin_parts.helpers import (
    all_roles as _all_roles,
    allowed_roles_to_create as _allowed_roles_to_create,
    current_role as _current_role,
    ordered_roles as _ordered_roles,
    require_admin_or_shelter_director_role as _require_admin_or_shelter_director,
    require_admin_role as _require_admin,
)


def admin_users_view():
    from app import ROLE_LABELS, init_db

    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("auth.staff_home"))

    init_db()

    allowed_roles = _allowed_roles_to_create()
    kind = "pg" if current_app.config.get("DATABASE_URL") else "sqlite"

    q = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "last_name").strip()

    where = []
    params = []

    if q:
        like_op = "ILIKE" if kind == "pg" else "LIKE"
        ph = "%s" if kind == "pg" else "?"
        where.append(
            "("
            f"COALESCE(first_name, '') {like_op} {ph} OR "
            f"COALESCE(last_name, '') {like_op} {ph}"
            ")"
        )
        pattern = f"%{q}%"
        params.extend([pattern, pattern])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    if sort == "first_name":
        if kind == "pg":
            order_sql = "ORDER BY first_name ASC NULLS LAST, last_name ASC NULLS LAST, created_at DESC"
        else:
            order_sql = "ORDER BY first_name IS NULL, first_name ASC, last_name IS NULL, last_name ASC, created_at DESC"
    elif sort == "role":
        if kind == "pg":
            order_sql = """
                ORDER BY CASE role
                    WHEN 'admin' THEN 1
                    WHEN 'shelter_director' THEN 2
                    WHEN 'case_manager' THEN 3
                    WHEN 'ra' THEN 4
                    WHEN 'staff' THEN 5
                    ELSE 99
                END,
                last_name ASC NULLS LAST,
                first_name ASC NULLS LAST,
                created_at DESC
            """
        else:
            order_sql = """
                ORDER BY CASE role
                    WHEN 'admin' THEN 1
                    WHEN 'shelter_director' THEN 2
                    WHEN 'case_manager' THEN 3
                    WHEN 'ra' THEN 4
                    WHEN 'staff' THEN 5
                    ELSE 99
                END,
                last_name IS NULL,
                last_name ASC,
                first_name IS NULL,
                first_name ASC,
                created_at DESC
            """
    else:
        sort = "last_name"
        if kind == "pg":
            order_sql = "ORDER BY last_name ASC NULLS LAST, first_name ASC NULLS LAST, created_at DESC"
        else:
            order_sql = "ORDER BY last_name IS NULL, last_name ASC, first_name IS NULL, first_name ASC, created_at DESC"

    users = db_fetchall(
        f"""
        SELECT id, first_name, last_name, username, role, is_active, created_at, mobile_phone
        FROM staff_users
        {where_sql}
        {order_sql}
        """,
        tuple(params),
    )

    return render_template(
        "admin_users.html",
        users=users,
        fmt_dt=fmt_dt,
        roles=_ordered_roles(allowed_roles),
        all_roles=_ordered_roles(_all_roles()),
        ROLE_LABELS=ROLE_LABELS,
        current_role=_current_role(),
        q=q,
        sort=sort,
    )


def admin_add_user_view():
    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("auth.staff_home"))

    return render_template("admin_user_form.html", mode="add", user=None)


def admin_edit_user_view(user_id: int):
    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("auth.staff_home"))

    rows = db_fetchall(
        "SELECT id, first_name, last_name, username, role, is_active, created_at, mobile_phone FROM staff_users WHERE id = %s"
        if current_app.config.get("DATABASE_URL")
        else "SELECT id, first_name, last_name, username, role, is_active, created_at, mobile_phone FROM staff_users WHERE id = ?",
        (user_id,),
    )

    if not rows:
        flash("User not found.", "error")
        return redirect(url_for("admin.admin_users"))

    return render_template("admin_user_form.html", mode="edit", user=rows[0])


def admin_set_user_active_view(user_id: int):
    role = _current_role()

    if role not in {"admin", "shelter_director"}:
        flash("Not allowed.", "error")
        return redirect(url_for("auth.staff_home"))

    active = (request.form.get("active") or "").strip()
    if active not in ["0", "1"]:
        flash("Invalid action.", "error")
        return redirect(url_for("admin.admin_users"))

    is_active_value = active == "1"

    db_execute(
        "UPDATE staff_users SET is_active = %s WHERE id = %s"
        if current_app.config.get("DATABASE_URL")
        else "UPDATE staff_users SET is_active = ? WHERE id = ?",
        (is_active_value if current_app.config.get("DATABASE_URL") else (1 if is_active_value else 0), user_id),
    )

    log_action(
        "staff_user",
        user_id,
        None,
        session.get("staff_user_id"),
        "set_active",
        f"active={active}",
    )

    flash("User updated.", "ok")
    return redirect(url_for("admin.admin_users"))


def admin_set_user_role_view(user_id: int):
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    new_role = (request.form.get("role") or "").strip()
    if new_role not in _all_roles():
        flash("Invalid role.", "error")
        return redirect(url_for("admin.admin_users"))

    db_execute(
        "UPDATE staff_users SET role = %s WHERE id = %s"
        if current_app.config.get("DATABASE_URL")
        else "UPDATE staff_users SET role = ? WHERE id = ?",
        (new_role, user_id),
    )

    log_action(
        "staff_user",
        user_id,
        None,
        session.get("staff_user_id"),
        "set_role",
        f"role={new_role}",
    )

    flash("Role updated.", "ok")
    return redirect(url_for("admin.admin_users"))


def admin_reset_user_password_view(user_id: int):
    from app import MIN_STAFF_PASSWORD_LEN
    from werkzeug.security import generate_password_hash

    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    password = (request.form.get("password") or "").strip()
    if len(password) < MIN_STAFF_PASSWORD_LEN:
        flash(f"Password must be at least {MIN_STAFF_PASSWORD_LEN} characters.", "error")
        return redirect(url_for("admin.admin_users"))

    db_execute(
        "UPDATE staff_users SET password_hash = %s WHERE id = %s"
        if current_app.config.get("DATABASE_URL")
        else "UPDATE staff_users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(password), user_id),
    )

    log_action(
        "staff_user",
        user_id,
        None,
        session.get("staff_user_id"),
        "reset_password",
        "Admin reset staff password",
    )

    flash("Password reset.", "ok")
    return redirect(url_for("admin.admin_users"))
