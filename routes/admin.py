from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, abort, current_app, g, redirect, render_template, request, session, url_for, flash

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall
from core.helpers import fmt_dt, utcnow_iso


admin = Blueprint("admin", __name__)


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


@admin.route("/staff/admin/users", methods=["GET", "POST"])
@require_login
@require_shelter
def admin_users():
    from app import MIN_STAFF_PASSWORD_LEN, ROLE_LABELS, init_db

    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("auth.staff_home"))

    init_db()

    allowed_roles = _allowed_roles_to_create()

    if request.method == "POST":
        from werkzeug.security import generate_password_hash

        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        role = (request.form.get("role") or "staff").strip()

        if not username or not password:
            flash("Username and password required.", "error")
            return redirect(url_for("admin.admin_users"))

        if len(password) < MIN_STAFF_PASSWORD_LEN:
            flash(f"Password must be at least {MIN_STAFF_PASSWORD_LEN} characters.", "error")
            return redirect(url_for("admin.admin_users"))

        if role not in allowed_roles:
            flash("You are not allowed to create that role.", "error")
            return redirect(url_for("admin.admin_users"))

        try:
            db_execute(
                "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (%s, %s, %s, %s, %s)"
                if g.get("db_kind") == "pg"
                else "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, generate_password_hash(password), role, True, utcnow_iso()),
            )
            log_action(
                "staff_user",
                None,
                session.get("shelter"),
                session.get("staff_user_id"),
                "create_user",
                f"created_username={username} role={role}",
            )
            flash("User created.", "ok")
        except Exception:
            flash("Username already exists.", "error")

        return redirect(url_for("admin.admin_users"))

    users = db_fetchall(
        "SELECT id, username, role, is_active, created_at FROM staff_users ORDER BY created_at DESC"
    )

    return render_template(
        "admin_users.html",
        users=users,
        fmt_dt=fmt_dt,
        roles=sorted(allowed_roles),
        ROLE_LABELS=ROLE_LABELS,
    )


@admin.post("/staff/admin/users/<int:user_id>/set-active")
@require_login
@require_shelter
def admin_set_user_active(user_id: int):
    role = (session.get("role") or "").strip()

    if role not in {"admin", "shelter_director"}:
        flash("Not allowed.", "error")
        return redirect(url_for("auth.staff_home"))

    active = (request.form.get("active") or "").strip()

    if active not in ["0", "1"]:
        flash("Invalid action.", "error")
        return redirect(url_for("admin.admin_users"))

    if g.get("db_kind") == "pg":
        db_execute(
            "UPDATE staff_users SET is_active = %s WHERE id = %s",
            (active == "1", user_id),
        )
    else:
        db_execute(
            "UPDATE staff_users SET is_active = ? WHERE id = ?",
            (1 if active == "1" else 0, user_id),
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


@admin.route("/staff/admin/audit-log")
@require_login
@require_shelter
def staff_audit_log():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    sql = (
        """
        SELECT a.*, su.username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        ORDER BY a.id DESC
        LIMIT %s
        """
        if current_app.config.get("DATABASE_URL")
        else """
        SELECT a.*, su.username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        ORDER BY a.id DESC
        LIMIT ?
        """
    )

    rows = db_fetchall(sql, (200,))

    return render_template("staff_audit_log.html", rows=rows)


@admin.get("/staff/admin/audit-log/csv")
@require_login
@require_shelter
def staff_audit_log_csv():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    where_sql, params = _audit_where_from_request()
    created_expr = "a.created_at::text" if g.get("db_kind") == "pg" else "a.created_at"

    sql = (
        f"SELECT a.id, a.entity_type, a.entity_id, a.shelter, "
        f"COALESCE(su.username, '') AS staff_username, "
        f"a.action_type, COALESCE(a.action_details, '') AS action_details, "
        f"{created_expr} AS created_at "
        f"FROM audit_log a "
        f"LEFT JOIN staff_users su ON su.id = a.staff_user_id "
        f"{where_sql} "
        f"ORDER BY a.id DESC"
    )

    rows = db_fetchall(sql, params)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "entity_type", "entity_id", "shelter", "staff_username", "action_type", "action_details", "created_at"])

    for r in rows:
        if isinstance(r, dict):
            w.writerow([
                r.get("id", ""),
                r.get("entity_type", ""),
                r.get("entity_id", ""),
                r.get("shelter", ""),
                r.get("staff_username", ""),
                r.get("action_type", ""),
                r.get("action_details", ""),
                r.get("created_at", ""),
            ])
        else:
            w.writerow(list(r))

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )


@admin.route("/admin/wipe-all-data", methods=["POST"])
@require_login
@require_shelter
def wipe_all_data():
    from app import ENABLE_DANGEROUS_ADMIN_ROUTES, init_db

    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    if not ENABLE_DANGEROUS_ADMIN_ROUTES:
        abort(404)

    init_db()

    db_execute("TRUNCATE TABLE attendance_events RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM attendance_events")
    db_execute("TRUNCATE TABLE leave_requests RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM leave_requests")
    db_execute("TRUNCATE TABLE transport_requests RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM transport_requests")
    db_execute("TRUNCATE TABLE residents RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM residents")
    db_execute("TRUNCATE TABLE audit_log RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM audit_log")

    log_action("admin", None, None, session.get("staff_user_id"), "wipe_all_data", "Wiped attendance, leave, transport, residents, audit_log")
    return "All non staff data wiped."


@admin.route("/admin/recreate-schema", methods=["POST"])
@require_login
@require_shelter
def recreate_schema():
    from app import ENABLE_DANGEROUS_ADMIN_ROUTES, init_db

    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    if not ENABLE_DANGEROUS_ADMIN_ROUTES:
        abort(404)

    init_db()

    if g.get("db_kind") == "pg":
        db_execute("DROP TABLE IF EXISTS attendance_events CASCADE")
        db_execute("DROP TABLE IF EXISTS leave_requests CASCADE")
        db_execute("DROP TABLE IF EXISTS transport_requests CASCADE")
        db_execute("DROP TABLE IF EXISTS residents CASCADE")
        db_execute("DROP TABLE IF EXISTS audit_log CASCADE")
        db_execute("DROP TABLE IF EXISTS resident_transfers CASCADE")
        db_execute("DROP TABLE IF EXISTS rate_limit_events CASCADE")
    else:
        db_execute("DROP TABLE IF EXISTS attendance_events")
        db_execute("DROP TABLE IF EXISTS leave_requests")
        db_execute("DROP TABLE IF EXISTS transport_requests")
        db_execute("DROP TABLE IF EXISTS residents")
        db_execute("DROP TABLE IF EXISTS audit_log")
        db_execute("DROP TABLE IF EXISTS resident_transfers")

    init_db()
    log_action("admin", None, None, session.get("staff_user_id"), "recreate_schema", "Dropped and recreated tables")
    return "Schema recreated."
