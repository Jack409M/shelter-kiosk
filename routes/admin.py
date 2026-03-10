from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, abort, current_app, g, redirect, render_template, request, session, url_for, flash

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall
from core.helpers import fmt_dt


admin = Blueprint("admin", __name__)

ROLE_ORDER = ["admin", "shelter_director", "case_manager", "ra", "staff"]


def _current_role() -> str:
    return (session.get("role") or "").strip()


def _require_admin() -> bool:
    return _current_role() == "admin"


def _require_admin_or_shelter_director() -> bool:
    return _current_role() in {"admin", "shelter_director"}


def _allowed_roles_to_create():
    if _require_admin():
        return {"admin", "shelter_director", "staff", "case_manager", "ra"}

    if _current_role() == "shelter_director":
        return {"staff", "case_manager", "ra"}

    return set()


def _all_roles():
    return {"admin", "shelter_director", "staff", "case_manager", "ra"}


def _ordered_roles(role_set):
    return [r for r in ROLE_ORDER if r in role_set]


def _audit_where_from_request():
    kind = g.get("db_kind")
    where = []
    params = []

    def add_eq(field, key):
        v = (request.args.get(key) or "").strip()
        if v:
            where.append(f"{field} = " + ("%s" if kind == "pg" else "?"))
            params.append(v)

    add_eq("a.shelter", "shelter")
    add_eq("a.entity_type", "entity_type")
    add_eq("a.action_type", "action_type")

    staff_user_id = (request.args.get("staff_user_id") or "").strip()
    if staff_user_id.isdigit():
        where.append("a.staff_user_id = " + ("%s" if kind == "pg" else "?"))
        params.append(int(staff_user_id))

    q = (request.args.get("q") or "").strip()
    if q:
        like_op = "ILIKE" if kind == "pg" else "LIKE"
        ph = "%s" if kind == "pg" else "?"
        where.append(
            "("
            f"CAST(a.id AS TEXT) {like_op} {ph} OR "
            f"COALESCE(a.action_details, '') {like_op} {ph} OR "
            f"COALESCE(a.action_type, '') {like_op} {ph} OR "
            f"COALESCE(a.entity_type, '') {like_op} {ph} OR "
            f"COALESCE(su.username, '') {like_op} {ph}"
            ")"
        )
        pat = f"%{q}%"
        params.extend([pat, pat, pat, pat, pat])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    return where_sql, tuple(params)


@admin.route("/staff/admin/users", methods=["GET"])
@require_login
@require_shelter
def admin_users():
    from app import ROLE_LABELS, init_db

    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("auth.staff_home"))

    init_db()

    allowed_roles = _allowed_roles_to_create()

    users = db_fetchall(
        "SELECT id, first_name, last_name, username, role, is_active, created_at "
        "FROM staff_users "
        "ORDER BY last_name ASC NULLS LAST, first_name ASC NULLS LAST, created_at DESC"
        if current_app.config.get("DATABASE_URL")
        else
        "SELECT id, first_name, last_name, username, role, is_active, created_at "
        "FROM staff_users "
        "ORDER BY last_name IS NULL, last_name ASC, first_name IS NULL, first_name ASC, created_at DESC"
    )

    return render_template(
        "admin_users.html",
        users=users,
        fmt_dt=fmt_dt,
        roles=_ordered_roles(allowed_roles),
        all_roles=_ordered_roles(_all_roles()),
        ROLE_LABELS=ROLE_LABELS,
        current_role=_current_role(),
    )


@admin.route("/staff/admin/users/add", methods=["GET"])
@require_login
@require_shelter
def admin_add_user():
    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("auth.staff_home"))

    return render_template("admin_user_form.html", mode="add", user=None)


@admin.route("/staff/admin/users/<int:user_id>/edit", methods=["GET"])
@require_login
@require_shelter
def admin_edit_user(user_id: int):
    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("auth.staff_home"))

    rows = db_fetchall(
        "SELECT id, first_name, last_name, username, role, is_active, created_at FROM staff_users WHERE id = %s"
        if current_app.config.get("DATABASE_URL")
        else "SELECT id, first_name, last_name, username, role, is_active, created_at FROM staff_users WHERE id = ?",
        (user_id,),
    )

    if not rows:
        flash("User not found.", "error")
        return redirect(url_for("admin.admin_users"))

    return render_template("admin_user_form.html", mode="edit", user=rows[0])


@admin.post("/staff/admin/users/<int:user_id>/set-active")
@require_login
@require_shelter
def admin_set_user_active(user_id: int):
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
