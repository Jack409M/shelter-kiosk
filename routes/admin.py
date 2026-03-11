from __future__ import annotations

import csv
import io
from collections import Counter, deque

from flask import Blueprint, Response, abort, current_app, g, jsonify, redirect, render_template, request, session, url_for, flash

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall
from core.helpers import fmt_dt
from core.rate_limit import get_banned_ips_snapshot, get_locked_keys_snapshot, get_rate_limit_snapshot
from core.sms_sender import send_sms


admin = Blueprint("admin", __name__)

ROLE_ORDER = ["admin", "shelter_director", "case_manager", "ra", "staff"]


def _current_role() -> str:
    """Return the current logged in staff role from session."""
    return (session.get("role") or "").strip()


def _require_admin() -> bool:
    """Return True if the current user is an admin."""
    return _current_role() == "admin"


def _require_admin_or_shelter_director() -> bool:
    """Return True if the current user is admin or shelter director."""
    return _current_role() in {"admin", "shelter_director"}


def _allowed_roles_to_create():
    """Return the set of roles the current user is allowed to create."""
    if _require_admin():
        return {"admin", "shelter_director", "staff", "case_manager", "ra"}

    if _current_role() == "shelter_director":
        return {"staff", "case_manager", "ra"}

    return set()


def _all_roles():
    """Return every valid staff role in the system."""
    return {"admin", "shelter_director", "staff", "case_manager", "ra"}


def _ordered_roles(role_set):
    """Return roles ordered consistently for dropdowns and UI display."""
    return [r for r in ROLE_ORDER if r in role_set]


def _scalar_value(rows, default=0):
    """
    Safely extract a single scalar value from db_fetchall results.

    This handles both dict based PostgreSQL rows and tuple based SQLite rows.
    """
    if not rows:
        return default

    row = rows[0]

    if isinstance(row, dict):
        return next(iter(row.values()), default)

    if isinstance(row, (list, tuple)) and row:
        return row[0]

    return default


def _row_value(row, key: str, default=""):
    """Read a value from either a dict row or tuple like row."""
    if isinstance(row, dict):
        return row.get(key, default)

    try:
        return row[key]
    except Exception:
        return default


def _serialize_rows(rows, fields: list[str]) -> list[dict]:
    """Convert mixed DB rows into JSON safe dictionaries."""
    out = []

    for row in rows or []:
        item = {}
        for field in fields:
            value = _row_value(row, field, "")
            item[field] = "" if value is None else value
        out.append(item)

    return out


def _extract_detail_value(details: str, key: str) -> str:
    """
    Extract a key=value pair from an audit action_details string.

    Example:
        details = "reason=bad_password ip=1.2.3.4 username=jack"

    This helper expects one key=value pair per line if multiline data is used.
    """
    if not details:
        return ""

    prefix = f"{key}="
    for line in details.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip()

    return ""


def _build_attack_intelligence(rows):
    """
    Build attack summaries from recent failed login audit rows.

    Returns:
        top_attacking_ips
        targeted_usernames
    """
    ip_counter = Counter()
    username_counter = Counter()

    for row in rows or []:
        details = row.get("action_details", "") if isinstance(row, dict) else ""
        ip = _extract_detail_value(details, "ip")
        username = _extract_detail_value(details, "username")

        if ip:
            ip_counter[ip] += 1

        if username:
            username_counter[username] += 1

    top_attacking_ips = [
        {"ip": ip, "attempts": attempts}
        for ip, attempts in ip_counter.most_common(10)
    ]

    targeted_usernames = [
        {"username": username, "attempts": attempts}
        for username, attempts in username_counter.most_common(10)
    ]

    return top_attacking_ips, targeted_usernames


def _build_locked_username_snapshot():
    """
    Convert generic locked rate limit keys into dashboard friendly username rows.

    Only username lock keys are included here.
    """
    rows = []

    for row in get_locked_keys_snapshot():
        key = str(row.get("key", ""))
        prefix = "staff_login_username_lock:"

        if not key.startswith(prefix):
            continue

        rows.append(
            {
                "username": key[len(prefix):],
                "seconds_remaining": row.get("seconds_remaining", 0),
                "key": key,
            }
        )

    rows.sort(key=lambda item: int(item["seconds_remaining"]), reverse=True)
    return rows


def _build_recent_staff_sessions(limit: int = 12) -> list[dict]:
    """
    Approximate active staff sessions from recent login and logout audit events.

    This is activity based, not a true server side session store.
    A user is treated as active when the latest auth event seen is login.
    """
    kind = g.get("db_kind")

    rows = db_fetchall(
        """
        SELECT
            a.action_type,
            a.action_details,
            a.created_at,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        WHERE a.action_type IN ('login', 'logout', 'profile_update', 'reset_password', 'set_role', 'set_active')
          AND NULLIF(a.created_at, '')::timestamptz >= NOW() - INTERVAL '12 hours'
        ORDER BY a.id DESC
        LIMIT %s
        """
        if kind == "pg"
        else """
        SELECT
            a.action_type,
            a.action_details,
            a.created_at,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        WHERE a.action_type IN ('login', 'logout', 'profile_update', 'reset_password', 'set_role', 'set_active')
          AND a.created_at >= datetime('now', '-12 hours')
        ORDER BY a.id DESC
        LIMIT ?
        """,
        (250,),
    )

    sessions = {}

    for row in rows or []:
        username = (_row_value(row, "staff_username", "") or "").strip()
        if not username:
            details = _row_value(row, "action_details", "") or ""
            username = _extract_detail_value(details, "username")

        if not username or username in sessions:
            continue

        action_type = (_row_value(row, "action_type", "") or "").strip()
        created_at = _row_value(row, "created_at", "") or ""
        details = _row_value(row, "action_details", "") or ""

        sessions[username] = {
            "username": username,
            "status": "active" if action_type == "login" else "ended",
            "last_seen": created_at,
            "last_action": action_type,
            "details": details,
        }

    active_rows = [row for row in sessions.values() if row["status"] == "active"]
    active_rows.sort(key=lambda item: str(item.get("last_seen", "")), reverse=True)
    return active_rows[:limit]


def _security_alert_cooldown_hit(key: str, window_seconds: int) -> bool:
    """
    Return True when this alert key was already fired inside the cooldown window.

    PostgreSQL uses rate_limit_events.
    SQLite uses in memory buckets.
    """
    import time

    if g.get("db_kind") == "pg":
        db_execute("INSERT INTO rate_limit_events (k) VALUES (%s)", (key,))
        rows = db_fetchall(
            """
            SELECT COUNT(1) AS c
            FROM rate_limit_events
            WHERE k = %s
              AND created_at >= NOW() - (%s * INTERVAL '1 second')
            """,
            (key, window_seconds),
        )
        count = int((rows[0]["c"] if isinstance(rows[0], dict) else rows[0][0])) if rows else 0
        return count > 1

    store = current_app.config.setdefault("_SECURITY_ALERT_BUCKETS_MEM", {})
    bucket = store.get(key)
    now = time.time()

    if bucket is None:
        bucket = deque()
        store[key] = bucket

    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if bucket:
        return True

    bucket.append(now)
    return False


def _load_admin_alert_numbers() -> list[str]:
    """Return all active admin mobile phone numbers."""
    try:
        rows = db_fetchall(
            "SELECT mobile_phone FROM staff_users WHERE role = %s AND is_active = %s AND COALESCE(mobile_phone, '') <> ''"
            if g.get("db_kind") == "pg"
            else "SELECT mobile_phone FROM staff_users WHERE role = ? AND is_active = ? AND COALESCE(mobile_phone, '') <> ''",
            ("admin", True if g.get("db_kind") == "pg" else 1),
        )
    except Exception:
        return []

    numbers = []
    for row in rows or []:
        phone = (_row_value(row, "mobile_phone", "") or "").strip()
        if phone and phone not in numbers:
            numbers.append(phone)

    return numbers


def _maybe_send_security_alerts(*, failed_login_count: int, top_attacking_ips: list[dict], targeted_usernames: list[dict], banned_ips: list[dict], locked_usernames: list[dict]) -> None:
    """Send throttled SMS alerts for serious security conditions."""
    numbers = _load_admin_alert_numbers()
    if not numbers:
        return

    alert_key = ""
    alert_message = ""

    if banned_ips:
        row = banned_ips[0]
        alert_key = f"security_alert:banned_ip:{row.get('ip', 'unknown')}"
        alert_message = f"DWC security alert. An IP is banned right now. IP {row.get('ip', 'unknown')}. Review the admin dashboard immediately."
    elif locked_usernames:
        row = locked_usernames[0]
        alert_key = f"security_alert:locked_user:{row.get('username', 'unknown')}"
        alert_message = f"DWC security alert. A staff username is locked right now. Username {row.get('username', 'unknown')}. Review the admin dashboard immediately."
    elif top_attacking_ips and int(top_attacking_ips[0].get("attempts", 0)) >= 10:
        row = top_attacking_ips[0]
        alert_key = f"security_alert:attacker_ip:{row.get('ip', 'unknown')}"
        alert_message = f"DWC security alert. High volume login failures detected from IP {row.get('ip', 'unknown')} with {row.get('attempts', 0)} attempts in the last 24 hours."
    elif targeted_usernames and int(targeted_usernames[0].get("attempts", 0)) >= 10:
        row = targeted_usernames[0]
        alert_key = f"security_alert:targeted_user:{row.get('username', 'unknown')}"
        alert_message = f"DWC security alert. Username {row.get('username', 'unknown')} has been targeted {row.get('attempts', 0)} times in the last 24 hours."
    elif failed_login_count >= 15:
        alert_key = "security_alert:failed_logins_24h"
        alert_message = f"DWC security alert. Failed logins reached {failed_login_count} in the last 24 hours. Review the admin dashboard."

    if not alert_key or not alert_message:
        return

    if _security_alert_cooldown_hit(alert_key, 1800):
        return

    for number in numbers:
        try:
            send_sms(number, alert_message)
        except Exception:
            continue


def _build_admin_dashboard_payload(*, send_alerts: bool = False) -> dict:
    """Build a single shared payload for the dashboard page and live JSON feed."""
    is_pg = bool(current_app.config.get("DATABASE_URL"))

    total_users = _scalar_value(
        db_fetchall("SELECT COUNT(*) AS c FROM staff_users")
    )

    active_users = _scalar_value(
        db_fetchall(
            "SELECT COUNT(*) AS c FROM staff_users WHERE is_active = %s"
            if is_pg
            else "SELECT COUNT(*) AS c FROM staff_users WHERE is_active = ?",
            (True if is_pg else 1,),
        )
    )

    recent_audit = db_fetchall(
        """
        SELECT
            a.id,
            a.entity_type,
            a.action_type,
            a.action_details,
            a.created_at,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        ORDER BY a.id DESC
        LIMIT %s
        """
        if is_pg
        else """
        SELECT
            a.id,
            a.entity_type,
            a.action_type,
            a.action_details,
            a.created_at,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        ORDER BY a.id DESC
        LIMIT ?
        """,
        (10,),
    )

    failed_login_count = _scalar_value(
        db_fetchall(
            """
            SELECT COUNT(*) AS c
            FROM audit_log
            WHERE action_type = 'login_failed'
              AND NULLIF(created_at, '')::timestamptz >= NOW() - INTERVAL '24 hours'
            """
            if is_pg
            else """
            SELECT COUNT(*) AS c
            FROM audit_log
            WHERE action_type = 'login_failed'
              AND created_at >= datetime('now', '-24 hours')
            """
        )
    )

    failed_logins_24h = db_fetchall(
        """
        SELECT
            a.id,
            a.action_type,
            a.action_details,
            a.created_at,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        WHERE a.action_type = 'login_failed'
          AND NULLIF(a.created_at, '')::timestamptz >= NOW() - INTERVAL '24 hours'
        ORDER BY a.id DESC
        LIMIT %s
        """
        if is_pg
        else """
        SELECT
            a.id,
            a.action_type,
            a.action_details,
            a.created_at,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        WHERE a.action_type = 'login_failed'
          AND a.created_at >= datetime('now', '-24 hours')
        ORDER BY a.id DESC
        LIMIT ?
        """,
        (200,),
    )

    recent_failed_logins = failed_logins_24h[:10]
    top_attacking_ips, targeted_usernames = _build_attack_intelligence(failed_logins_24h)

    banned_ips = get_banned_ips_snapshot()
    locked_usernames = _build_locked_username_snapshot()
    rate_limit_activity = get_rate_limit_snapshot()
    recent_staff_sessions = _build_recent_staff_sessions()

    kiosk_security_events = db_fetchall(
        """
        SELECT action_type, action_details, created_at
        FROM audit_log
        WHERE action_type LIKE 'kiosk_%%'
        ORDER BY id DESC
        LIMIT %s
        """
        if is_pg
        else """
        SELECT action_type, action_details, created_at
        FROM audit_log
        WHERE action_type LIKE 'kiosk_%'
        ORDER BY id DESC
        LIMIT ?
        """,
        (10,),
    )

    if send_alerts:
        _maybe_send_security_alerts(
            failed_login_count=int(failed_login_count or 0),
            top_attacking_ips=top_attacking_ips,
            targeted_usernames=targeted_usernames,
            banned_ips=banned_ips,
            locked_usernames=locked_usernames,
        )

    return {
        "total_users": int(total_users or 0),
        "active_users": int(active_users or 0),
        "recent_audit": recent_audit,
        "failed_login_count": int(failed_login_count or 0),
        "recent_failed_logins": recent_failed_logins,
        "top_attacking_ips": top_attacking_ips,
        "targeted_usernames": targeted_usernames,
        "banned_ips": banned_ips,
        "locked_usernames": locked_usernames,
        "rate_limit_activity": rate_limit_activity,
        "kiosk_security_events": kiosk_security_events,
        "recent_staff_sessions": recent_staff_sessions,
        "live_payload": {
            "failed_login_count": int(failed_login_count or 0),
            "recent_audit": _serialize_rows(recent_audit, ["created_at", "staff_username", "action_type", "action_details"]),
            "recent_failed_logins": _serialize_rows(recent_failed_logins, ["created_at", "action_type", "action_details"]),
            "kiosk_security_events": _serialize_rows(kiosk_security_events, ["created_at", "action_type", "action_details"]),
            "recent_staff_sessions": recent_staff_sessions,
            "top_attacking_ips": top_attacking_ips,
            "targeted_usernames": targeted_usernames,
            "banned_ips": banned_ips,
            "locked_usernames": locked_usernames,
            "rate_limit_activity": rate_limit_activity,
        },
    }


def _audit_where_from_request():
    """
    Build dynamic WHERE filters for the audit CSV export endpoint.

    Supports filtering by:
    - shelter
    - entity_type
    - action_type
    - staff_user_id
    - free text query
    """
    kind = g.get("db_kind")
    where = []
    params = []

    def add_eq(field, key):
        value = (request.args.get(key) or "").strip()
        if value:
            where.append(f"{field} = " + ("%s" if kind == "pg" else "?"))
            params.append(value)

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
        pattern = f"%{q}%"
        params.extend([pattern, pattern, pattern, pattern, pattern])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    return where_sql, tuple(params)


@admin.route("/staff/admin/dashboard", methods=["GET"])
@require_login
@require_shelter
def admin_dashboard():
    """
    Main admin dashboard.

    Displays:
    - total users
    - active users
    - recent audit activity
    - failed login monitoring
    - attack intelligence
    - active defenses
    - kiosk security activity
    - recent staff access monitor
    """
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    payload = _build_admin_dashboard_payload(send_alerts=True)

    return render_template(
        "admin_dashboard.html",
        total_users=payload["total_users"],
        active_users=payload["active_users"],
        recent_audit=payload["recent_audit"],
        failed_login_count=payload["failed_login_count"],
        recent_failed_logins=payload["recent_failed_logins"],
        top_attacking_ips=payload["top_attacking_ips"],
        targeted_usernames=payload["targeted_usernames"],
        banned_ips=payload["banned_ips"],
        locked_usernames=payload["locked_usernames"],
        rate_limit_activity=payload["rate_limit_activity"],
        kiosk_security_events=payload["kiosk_security_events"],
        recent_staff_sessions=payload["recent_staff_sessions"],
        dashboard_live_url=url_for("admin.admin_dashboard_live"),
        fmt_dt=fmt_dt,
        current_role=_current_role(),
    )


@admin.route("/staff/admin/dashboard/live", methods=["GET"])
@require_login
@require_shelter
def admin_dashboard_live():
    """Return live dashboard JSON."""
    if not _require_admin():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = _build_admin_dashboard_payload(send_alerts=True)
    live_payload = payload["live_payload"]
    live_payload["ok"] = True
    return jsonify(live_payload)


@admin.route("/staff/admin/users", methods=["GET"])
@require_login
@require_shelter
def admin_users():
    """
    Staff user list page.

    Supports:
    - role based access
    - free text search
    - sorting by last name, first name, or role
    """
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
        SELECT id, first_name, last_name, username, role, is_active, created_at
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


@admin.route("/staff/admin/users/add", methods=["GET"])
@require_login
@require_shelter
def admin_add_user():
    """Render add user form."""
    if not _require_admin_or_shelter_director():
        flash("Admin or Shelter Director only.", "error")
        return redirect(url_for("auth.staff_home"))

    return render_template("admin_user_form.html", mode="add", user=None)


@admin.route("/staff/admin/users/<int:user_id>/edit", methods=["GET"])
@require_login
@require_shelter
def admin_edit_user(user_id: int):
    """Render edit user form for an existing staff user."""
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
    """Activate or deactivate a staff user account."""
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


@admin.post("/staff/admin/users/<int:user_id>/set-role")
@require_login
@require_shelter
def admin_set_user_role(user_id: int):
    """Change the role of a staff user."""
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


@admin.post("/staff/admin/users/<int:user_id>/reset-password")
@require_login
@require_shelter
def admin_reset_user_password(user_id: int):
    """Reset a staff user's password."""
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


@admin.route("/staff/admin/audit-log")
@require_login
@require_shelter
def staff_audit_log():
    """Render full audit log page for admins."""
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
    """Export filtered audit log rows as CSV."""
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
    writer = csv.writer(buf)
    writer.writerow(["id", "entity_type", "entity_id", "shelter", "staff_username", "action_type", "action_details", "created_at"])

    for row in rows:
        if isinstance(row, dict):
            writer.writerow([
                row.get("id", ""),
                row.get("entity_type", ""),
                row.get("entity_id", ""),
                row.get("shelter", ""),
                row.get("staff_username", ""),
                row.get("action_type", ""),
                row.get("action_details", ""),
                row.get("created_at", ""),
            ])
        else:
            writer.writerow(list(row))

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )


@admin.route("/admin/wipe-all-data", methods=["POST"])
@require_login
@require_shelter
def wipe_all_data():
    """
    Dangerous admin route.

    Deletes operational data for development resets when enabled by config.
    """
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

    log_action(
        "admin",
        None,
        None,
        session.get("staff_user_id"),
        "wipe_all_data",
        "Wiped attendance, leave, transport, residents, audit_log",
    )
    return "All non staff data wiped."


@admin.route("/admin/recreate-schema", methods=["POST"])
@require_login
@require_shelter
def recreate_schema():
    """
    Dangerous admin route.

    Drops and recreates schema for development resets when enabled by config.
    """
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

    log_action(
        "admin",
        None,
        None,
        session.get("staff_user_id"),
        "recreate_schema",
        "Dropped and recreated tables",
    )
    return "Schema recreated."
    
