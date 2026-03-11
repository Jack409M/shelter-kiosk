from __future__ import annotations

import csv
import io
from collections import Counter, deque

from flask import Blueprint, Response, abort, current_app, g, jsonify, redirect, render_template, request, session, url_for, flash

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall
from core.helpers import fmt_dt, utcnow_iso
from core.rate_limit import get_banned_ips_snapshot, get_locked_keys_snapshot, get_rate_limit_snapshot
from core.sms_sender import send_sms


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


def _scalar_value(rows, default=0):
    if not rows:
        return default

    row = rows[0]

    if isinstance(row, dict):
        return next(iter(row.values()), default)

    if isinstance(row, (list, tuple)) and row:
        return row[0]

    return default


def _row_value(row, key: str, default=""):
    if isinstance(row, dict):
        return row.get(key, default)

    try:
        return row[key]
    except Exception:
        return default


def _serialize_rows(rows, fields: list[str]) -> list[dict]:
    out = []

    for row in rows or []:
        item = {}
        for field in fields:
            value = _row_value(row, field, "")
            item[field] = "" if value is None else value
        out.append(item)

    return out


def _extract_detail_value(details: str, key: str) -> str:
    if not details:
        return ""

    prefix = f"{key}="
    for line in details.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip()

    return ""


def _build_attack_intelligence(rows):
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


def _load_security_settings() -> dict:
    kind = g.get("db_kind")
    rows = db_fetchall("SELECT * FROM security_settings ORDER BY id ASC LIMIT 1")
    row = rows[0] if rows else {}

    if not row:
        now = utcnow_iso()
        db_execute(
            """
            INSERT INTO security_settings (
                sms_system_enabled,
                kiosk_intake_enabled,
                admin_login_only_mode,
                security_alerts_enabled,
                failed_login_alert_threshold,
                attacker_ip_alert_threshold,
                targeted_username_alert_threshold,
                lockout_seconds,
                ip_ban_seconds,
                alert_cooldown_seconds,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            if kind == "pg"
            else """
            INSERT INTO security_settings (
                sms_system_enabled,
                kiosk_intake_enabled,
                admin_login_only_mode,
                security_alerts_enabled,
                failed_login_alert_threshold,
                attacker_ip_alert_threshold,
                targeted_username_alert_threshold,
                lockout_seconds,
                ip_ban_seconds,
                alert_cooldown_seconds,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                True if kind == "pg" else 1,
                True if kind == "pg" else 1,
                False if kind == "pg" else 0,
                True if kind == "pg" else 1,
                15,
                10,
                10,
                900,
                1800,
                1800,
                now,
                now,
            ),
        )
        rows = db_fetchall("SELECT * FROM security_settings ORDER BY id ASC LIMIT 1")
        row = rows[0] if rows else {}

    return {
        "sms_system_enabled": bool(_row_value(row, "sms_system_enabled", True)),
        "kiosk_intake_enabled": bool(_row_value(row, "kiosk_intake_enabled", True)),
        "admin_login_only_mode": bool(_row_value(row, "admin_login_only_mode", False)),
        "security_alerts_enabled": bool(_row_value(row, "security_alerts_enabled", True)),
        "failed_login_alert_threshold": int(_row_value(row, "failed_login_alert_threshold", 15) or 15),
        "attacker_ip_alert_threshold": int(_row_value(row, "attacker_ip_alert_threshold", 10) or 10),
        "targeted_username_alert_threshold": int(_row_value(row, "targeted_username_alert_threshold", 10) or 10),
        "lockout_seconds": int(_row_value(row, "lockout_seconds", 900) or 900),
        "ip_ban_seconds": int(_row_value(row, "ip_ban_seconds", 1800) or 1800),
        "alert_cooldown_seconds": int(_row_value(row, "alert_cooldown_seconds", 1800) or 1800),
    }


def _load_recent_security_incidents(limit: int = 10) -> list[dict]:
    kind = g.get("db_kind")

    rows = db_fetchall(
        """
        SELECT id, incident_type, severity, title, details, related_ip, related_username, status, created_at
        FROM security_incidents
        ORDER BY id DESC
        LIMIT %s
        """
        if kind == "pg"
        else """
        SELECT id, incident_type, severity, title, details, related_ip, related_username, status, created_at
        FROM security_incidents
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )

    incidents = []
    for row in rows or []:
        incidents.append(
            {
                "id": _row_value(row, "id", ""),
                "incident_type": _row_value(row, "incident_type", ""),
                "severity": _row_value(row, "severity", ""),
                "title": _row_value(row, "title", ""),
                "details": _row_value(row, "details", ""),
                "related_ip": _row_value(row, "related_ip", ""),
                "related_username": _row_value(row, "related_username", ""),
                "status": _row_value(row, "status", ""),
                "created_at": _row_value(row, "created_at", ""),
            }
        )

    return incidents


def _build_recent_staff_sessions(limit: int = 12) -> list[dict]:
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

        sessions[username] = {
            "username": username,
            "status": "active" if action_type == "login" else "ended",
            "last_seen": created_at,
            "last_action": action_type,
        }

    active_rows = [row for row in sessions.values() if row["status"] == "active"]
    active_rows.sort(key=lambda item: str(item.get("last_seen", "")), reverse=True)
    return active_rows[:limit]


def _security_alert_cooldown_hit(key: str, window_seconds: int) -> bool:
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


def _incident_exists_recently(incident_type: str, related_ip: str = "", related_username: str = "", window_seconds: int = 1800) -> bool:
    kind = g.get("db_kind")

    rows = db_fetchall(
        """
        SELECT id
        FROM security_incidents
        WHERE incident_type = %s
          AND COALESCE(related_ip, '') = %s
          AND COALESCE(related_username, '') = %s
          AND created_at >= NOW() - (%s * INTERVAL '1 second')
        ORDER BY id DESC
        LIMIT 1
        """
        if kind == "pg"
        else """
        SELECT id
        FROM security_incidents
        WHERE incident_type = ?
          AND COALESCE(related_ip, '') = ?
          AND COALESCE(related_username, '') = ?
          AND created_at >= datetime('now', '-' || ? || ' seconds')
        ORDER BY id DESC
        LIMIT 1
        """,
        (incident_type, related_ip or "", related_username or "", window_seconds),
    )
    return bool(rows)


def _create_security_incident(incident_type: str, severity: str, title: str, details: str, related_ip: str = "", related_username: str = "") -> None:
    if _incident_exists_recently(incident_type, related_ip, related_username):
        return

    now = utcnow_iso()
    kind = g.get("db_kind")

    db_execute(
        """
        INSERT INTO security_incidents (
            incident_type,
            severity,
            title,
            details,
            related_ip,
            related_username,
            status,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        if kind == "pg"
        else """
        INSERT INTO security_incidents (
            incident_type,
            severity,
            title,
            details,
            related_ip,
            related_username,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (incident_type, severity, title, details, related_ip or "", related_username or "", "open", now, now),
    )


def _maybe_create_security_incidents(*, failed_login_count: int, top_attacking_ips: list[dict], targeted_usernames: list[dict], banned_ips: list[dict], locked_usernames: list[dict], settings: dict) -> None:
    ip_threshold = settings["attacker_ip_alert_threshold"]
    user_threshold = settings["targeted_username_alert_threshold"]
    failed_threshold = settings["failed_login_alert_threshold"]

    if banned_ips:
        row = banned_ips[0]
        _create_security_incident(
            "banned_ip",
            "high",
            "Banned IP Active",
            f"An IP is currently banned for hostile activity. ip={row.get('ip', '')}",
            related_ip=row.get("ip", ""),
        )

    if locked_usernames:
        row = locked_usernames[0]
        _create_security_incident(
            "locked_username",
            "high",
            "Locked Username Active",
            f"A username is currently locked due to repeated login failures. username={row.get('username', '')}",
            related_username=row.get("username", ""),
        )

    if top_attacking_ips and int(top_attacking_ips[0].get("attempts", 0)) >= ip_threshold:
        row = top_attacking_ips[0]
        _create_security_incident(
            "attacker_ip_threshold",
            "high",
            "Attacker IP Threshold Reached",
            f"IP {row.get('ip', '')} reached {row.get('attempts', 0)} failed login attempts.",
            related_ip=row.get("ip", ""),
        )

    if targeted_usernames and int(targeted_usernames[0].get("attempts", 0)) >= user_threshold:
        row = targeted_usernames[0]
        _create_security_incident(
            "targeted_username_threshold",
            "high",
            "Username Targeting Threshold Reached",
            f"Username {row.get('username', '')} reached {row.get('attempts', 0)} failed login attempts.",
            related_username=row.get("username", ""),
        )

    if failed_login_count >= failed_threshold:
        _create_security_incident(
            "failed_logins_threshold",
            "medium",
            "Failed Login Threshold Reached",
            f"Failed logins reached {failed_login_count} in the last 24 hours.",
        )


def _maybe_send_security_alerts(*, failed_login_count: int, top_attacking_ips: list[dict], targeted_usernames: list[dict], banned_ips: list[dict], locked_usernames: list[dict], settings: dict) -> None:
    if not settings["security_alerts_enabled"]:
        return

    if not settings["sms_system_enabled"]:
        return

    numbers = _load_admin_alert_numbers()
    if not numbers:
        return

    cooldown = settings["alert_cooldown_seconds"]

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
    elif top_attacking_ips and int(top_attacking_ips[0].get("attempts", 0)) >= settings["attacker_ip_alert_threshold"]:
        row = top_attacking_ips[0]
        alert_key = f"security_alert:attacker_ip:{row.get('ip', 'unknown')}"
        alert_message = f"DWC security alert. High volume login failures detected from IP {row.get('ip', 'unknown')} with {row.get('attempts', 0)} attempts in the last 24 hours."
    elif targeted_usernames and int(targeted_usernames[0].get("attempts", 0)) >= settings["targeted_username_alert_threshold"]:
        row = targeted_usernames[0]
        alert_key = f"security_alert:targeted_user:{row.get('username', 'unknown')}"
        alert_message = f"DWC security alert. Username {row.get('username', 'unknown')} has been targeted {row.get('attempts', 0)} times in the last 24 hours."
    elif failed_login_count >= settings["failed_login_alert_threshold"]:
        alert_key = "security_alert:failed_logins_24h"
        alert_message = f"DWC security alert. Failed logins reached {failed_login_count} in the last 24 hours. Review the admin dashboard."

    if not alert_key or not alert_message:
        return

    if _security_alert_cooldown_hit(alert_key, cooldown):
        return

    for number in numbers:
        try:
            send_sms(number, alert_message)
        except Exception:
            continue


def _build_admin_dashboard_payload(*, send_alerts: bool = False) -> dict:
    is_pg = bool(current_app.config.get("DATABASE_URL"))
    settings = _load_security_settings()

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

    _maybe_create_security_incidents(
        failed_login_count=int(failed_login_count or 0),
        top_attacking_ips=top_attacking_ips,
        targeted_usernames=targeted_usernames,
        banned_ips=banned_ips,
        locked_usernames=locked_usernames,
        settings=settings,
    )

    recent_security_incidents = _load_recent_security_incidents()

    if send_alerts:
        _maybe_send_security_alerts(
            failed_login_count=int(failed_login_count or 0),
            top_attacking_ips=top_attacking_ips,
            targeted_usernames=targeted_usernames,
            banned_ips=banned_ips,
            locked_usernames=locked_usernames,
            settings=settings,
        )

    return {
        "settings": settings,
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
        "recent_security_incidents": recent_security_incidents,
        "live_payload": {
            "settings": settings,
            "failed_login_count": int(failed_login_count or 0),
            "recent_audit": _serialize_rows(recent_audit, ["created_at", "staff_username", "action_type", "action_details"]),
            "recent_failed_logins": _serialize_rows(recent_failed_logins, ["created_at", "action_type", "action_details"]),
            "kiosk_security_events": _serialize_rows(kiosk_security_events, ["created_at", "action_type", "action_details"]),
            "recent_staff_sessions": recent_staff_sessions,
            "recent_security_incidents": recent_security_incidents,
            "top_attacking_ips": top_attacking_ips,
            "targeted_usernames": targeted_usernames,
            "banned_ips": banned_ips,
            "locked_usernames": locked_usernames,
            "rate_limit_activity": rate_limit_activity,
        },
    }


def _audit_where_from_request():
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
        recent_security_incidents=payload["recent_security_incidents"],
        security_settings=payload["settings"],
        dashboard_live_url=url_for("admin.admin_dashboard_live"),
        fmt_dt=fmt_dt,
        current_role=_current_role(),
    )


@admin.route("/staff/admin/dashboard/live", methods=["GET"])
@require_login
@require_shelter
def admin_dashboard_live():
    if not _require_admin():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = _build_admin_dashboard_payload(send_alerts=True)
    live_payload = payload["live_payload"]
    live_payload["ok"] = True
    return jsonify(live_payload)


@admin.post("/staff/admin/security-settings/update")
@require_login
@require_shelter
def admin_update_security_settings():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    allowed_fields = {
        "sms_system_enabled",
        "kiosk_intake_enabled",
        "admin_login_only_mode",
        "security_alerts_enabled",
    }

    field = (request.form.get("field") or "").strip()
    value = (request.form.get("value") or "").strip()

    if field not in allowed_fields:
        flash("Invalid security setting.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    if value not in {"0", "1"}:
        flash("Invalid security setting value.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    bool_value = value == "1"
    kind = g.get("db_kind")
    now = utcnow_iso()

    db_execute(
        f"UPDATE security_settings SET {field} = " + ("%s" if kind == "pg" else "?") + ", updated_at = " + ("%s" if kind == "pg" else "?") + " WHERE id = (SELECT id FROM security_settings ORDER BY id ASC LIMIT 1)",
        (bool_value if kind == "pg" else (1 if bool_value else 0), now),
    )

    log_action(
        "security_settings",
        None,
        None,
        session.get("staff_user_id"),
        "security_setting_updated",
        f"field={field}\nvalue={value}",
    )

    flash("Security setting updated.", "ok")
    return redirect(url_for("admin.admin_dashboard"))


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
        "SELECT id, first_name, last_name, username, role, is_active, created_at, mobile_phone FROM staff_users WHERE id = %s"
        if current_app.config.get("DATABASE_URL")
        else "SELECT id, first_name, last_name, username, role, is_active, created_at, mobile_phone FROM staff_users WHERE id = ?",
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


@admin.post("/staff/admin/users/<int:user_id>/set-role")
@require_login
@require_shelter
def admin_set_user_role(user_id: int):
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
    db_execute("TRUNCATE TABLE security_incidents RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM security_incidents")

    log_action(
        "admin",
        None,
        None,
        session.get("staff_user_id"),
        "wipe_all_data",
        "Wiped attendance, leave, transport, residents, audit_log, security_incidents",
    )
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
        db_execute("DROP TABLE IF EXISTS security_incidents CASCADE")
        db_execute("DROP TABLE IF EXISTS security_settings CASCADE")
    else:
        db_execute("DROP TABLE IF EXISTS attendance_events")
        db_execute("DROP TABLE IF EXISTS leave_requests")
        db_execute("DROP TABLE IF EXISTS transport_requests")
        db_execute("DROP TABLE IF EXISTS residents")
        db_execute("DROP TABLE IF EXISTS audit_log")
        db_execute("DROP TABLE IF EXISTS resident_transfers")
        db_execute("DROP TABLE IF EXISTS security_incidents")
        db_execute("DROP TABLE IF EXISTS security_settings")

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
