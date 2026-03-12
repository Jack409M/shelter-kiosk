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


VALID_SHELTERS = {"abba", "haven", "gratitude"}


def _db_kind() -> str:
    return "pg" if current_app.config.get("DATABASE_URL") else "sqlite"


def _ph() -> str:
    return "%s" if _db_kind() == "pg" else "?"


def _form_context(**extra):
    from app import ROLE_LABELS

    context = {
        "roles": _ordered_roles(_allowed_roles_to_create()),
        "all_roles": _ordered_roles(_all_roles()),
        "ROLE_LABELS": ROLE_LABELS,
        "current_role": _current_role(),
    }
    context.update(extra)
    return context


def _normalize_selected_shelters(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for value in values:
        shelter = (value or "").strip().lower()
        if shelter in VALID_SHELTERS and shelter not in seen:
            cleaned.append(shelter)
            seen.add(shelter)

    return cleaned


def _load_staff_shelter_assignments(staff_user_id: int) -> set[str]:
    rows = db_fetchall(
        f"SELECT shelter FROM staff_shelter_assignments WHERE staff_user_id = {_ph()} ORDER BY shelter",
        (staff_user_id,),
    )

    shelters: set[str] = set()

    for row in rows:
        shelter = (row["shelter"] or "").strip().lower()
        if shelter:
            shelters.add(shelter)

    return shelters


def _save_staff_shelter_assignments(staff_user_id: int, shelters: list[str]) -> None:
    db_execute(
        f"DELETE FROM staff_shelter_assignments WHERE staff_user_id = {_ph()}",
        (staff_user_id,),
    )

    cleaned = _normalize_selected_shelters(shelters)

    for shelter in cleaned:
        db_execute(
            f"INSERT INTO staff_shelter_assignments (staff_user_id, shelter) VALUES ({_ph()}, {_ph()})",
            (staff_user_id, shelter),
        )


def admin_users_view():
    from app import ROLE_LABELS, init_db

    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("auth.staff_home"))

    init_db()

    allowed_roles = _allowed_roles_to_create()
    kind = _db_kind()

    q = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "last_name").strip()

    where = []
    params = []

    if q:
        like_op = "ILIKE" if kind == "pg" else "LIKE"
        ph = _ph()
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
    from app import MIN_STAFF_PASSWORD_LEN
    from werkzeug.security import generate_password_hash

    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("auth.staff_home"))

    allowed_roles = set(_allowed_roles_to_create())

    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        username = (request.form.get("username") or "").strip()
        role = (request.form.get("role") or "").strip()
        mobile_phone = (request.form.get("mobile_phone") or "").strip()
        password = (request.form.get("password") or "").strip()
        selected_shelters = request.form.getlist("shelters")

        form_user = {
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "role": role,
            "mobile_phone": mobile_phone,
            "is_active": 1,
        }
        assigned_shelters = set(_normalize_selected_shelters(selected_shelters))

        if not first_name or not last_name or not username or not role or not password:
            flash("First name, last name, username, role, and password are required.", "error")
            return render_template(
                "admin_user_form.html",
                **_form_context(
                    mode="add",
                    user=form_user,
                    assigned_shelters=assigned_shelters,
                ),
            )

        if role not in allowed_roles:
            flash("You are not allowed to create that role.", "error")
            return render_template(
                "admin_user_form.html",
                **_form_context(
                    mode="add",
                    user=form_user,
                    assigned_shelters=assigned_shelters,
                ),
            )

        if len(password) < MIN_STAFF_PASSWORD_LEN:
            flash(f"Password must be at least {MIN_STAFF_PASSWORD_LEN} characters.", "error")
            return render_template(
                "admin_user_form.html",
                **_form_context(
                    mode="add",
                    user=form_user,
                    assigned_shelters=assigned_shelters,
                ),
            )

        existing = db_fetchall(
            f"SELECT id FROM staff_users WHERE username = {_ph()}",
            (username,),
        )
        if existing:
            flash("Username already exists.", "error")
            return render_template(
                "admin_user_form.html",
                **_form_context(
                    mode="add",
                    user=form_user,
                    assigned_shelters=assigned_shelters,
                ),
            )

        if _db_kind() == "pg":
            created = db_fetchall(
                f"""
                INSERT INTO staff_users (first_name, last_name, username, password_hash, role, is_active, mobile_phone)
                VALUES ({_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()})
                RETURNING id
                """,
                (
                    first_name,
                    last_name,
                    username,
                    generate_password_hash(password),
                    role,
                    True,
                    mobile_phone or None,
                ),
            )
            new_user_id = created[0]["id"]
        else:
            db_execute(
                f"""
                INSERT INTO staff_users (first_name, last_name, username, password_hash, role, is_active, mobile_phone)
                VALUES ({_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()})
                """,
                (
                    first_name,
                    last_name,
                    username,
                    generate_password_hash(password),
                    role,
                    1,
                    mobile_phone or None,
                ),
            )
            created = db_fetchall(
                f"SELECT id FROM staff_users WHERE username = {_ph()} ORDER BY id DESC",
                (username,),
            )
            new_user_id = created[0]["id"]

        _save_staff_shelter_assignments(new_user_id, selected_shelters)

        log_action(
            "staff_user",
            new_user_id,
            None,
            session.get("staff_user_id"),
            "create",
            f"Created user username={username} role={role}",
        )

        flash("User created.", "ok")
        return redirect(url_for("admin.admin_users"))

    return render_template(
        "admin_user_form.html",
        **_form_context(
            mode="add",
            user=None,
            assigned_shelters=set(),
        ),
    )


def admin_edit_user_view(user_id: int):
    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("auth.staff_home"))

    rows = db_fetchall(
        f"""
        SELECT id, first_name, last_name, username, role, is_active, created_at, mobile_phone
        FROM staff_users
        WHERE id = {_ph()}
        """,
        (user_id,),
    )

    if not rows:
        flash("User not found.", "error")
        return redirect(url_for("admin.admin_users"))

    user = rows[0]
    allowed_roles = set(_allowed_roles_to_create())
    current_user_role = (user["role"] or "").strip()

    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        username = (request.form.get("username") or "").strip()
        role = (request.form.get("role") or "").strip()
        mobile_phone = (request.form.get("mobile_phone") or "").strip()
        selected_shelters = request.form.getlist("shelters")

        if not first_name or not last_name or not username or not role:
            flash("First name, last name, username, and role are required.", "error")
            user["first_name"] = first_name
            user["last_name"] = last_name
            user["username"] = username
            user["role"] = role
            user["mobile_phone"] = mobile_phone
            return render_template(
                "admin_user_form.html",
                **_form_context(
                    mode="edit",
                    user=user,
                    assigned_shelters=set(_normalize_selected_shelters(selected_shelters)),
                ),
            )

        if role not in _all_roles():
            flash("Invalid role.", "error")
            user["first_name"] = first_name
            user["last_name"] = last_name
            user["username"] = username
            user["role"] = role
            user["mobile_phone"] = mobile_phone
            return render_template(
                "admin_user_form.html",
                **_form_context(
                    mode="edit",
                    user=user,
                    assigned_shelters=set(_normalize_selected_shelters(selected_shelters)),
                ),
            )

        if not _require_admin() and role != current_user_role:
            flash("Only admins can change user roles.", "error")
            user["first_name"] = first_name
            user["last_name"] = last_name
            user["username"] = username
            user["role"] = current_user_role
            user["mobile_phone"] = mobile_phone
            return render_template(
                "admin_user_form.html",
                **_form_context(
                    mode="edit",
                    user=user,
                    assigned_shelters=set(_normalize_selected_shelters(selected_shelters)),
                ),
            )

        if _require_admin() and role not in allowed_roles and role != current_user_role:
            flash("You are not allowed to assign that role.", "error")
            user["first_name"] = first_name
            user["last_name"] = last_name
            user["username"] = username
            user["role"] = current_user_role
            user["mobile_phone"] = mobile_phone
            return render_template(
                "admin_user_form.html",
                **_form_context(
                    mode="edit",
                    user=user,
                    assigned_shelters=set(_normalize_selected_shelters(selected_shelters)),
                ),
            )

        existing = db_fetchall(
            f"SELECT id FROM staff_users WHERE username = {_ph()} AND id <> {_ph()}",
            (username, user_id),
        )
        if existing:
            flash("Username already exists.", "error")
            user["first_name"] = first_name
            user["last_name"] = last_name
            user["username"] = username
            user["role"] = role if _require_admin() else current_user_role
            user["mobile_phone"] = mobile_phone
            return render_template(
                "admin_user_form.html",
                **_form_context(
                    mode="edit",
                    user=user,
                    assigned_shelters=set(_normalize_selected_shelters(selected_shelters)),
                ),
            )

        final_role = role if _require_admin() else current_user_role

        db_execute(
            f"""
            UPDATE staff_users
            SET first_name = {_ph()},
                last_name = {_ph()},
                username = {_ph()},
                role = {_ph()},
                mobile_phone = {_ph()}
            WHERE id = {_ph()}
            """,
            (
                first_name,
                last_name,
                username,
                final_role,
                mobile_phone or None,
                user_id,
            ),
        )

        _save_staff_shelter_assignments(user_id, selected_shelters)

        log_action(
            "staff_user",
            user_id,
            None,
            session.get("staff_user_id"),
            "update",
            f"Updated user username={username} role={final_role}",
        )

        flash("User updated.", "ok")
        return redirect(url_for("admin.admin_users"))

    return render_template(
        "admin_user_form.html",
        **_form_context(
            mode="edit",
            user=user,
            assigned_shelters=_load_staff_shelter_assignments(user_id),
        ),
    )


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
        f"UPDATE staff_users SET is_active = {_ph()} WHERE id = {_ph()}",
        (is_active_value if _db_kind() == "pg" else (1 if is_active_value else 0), user_id),
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
        f"UPDATE staff_users SET role = {_ph()} WHERE id = {_ph()}",
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
        f"UPDATE staff_users SET password_hash = {_ph()} WHERE id = {_ph()}",
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
