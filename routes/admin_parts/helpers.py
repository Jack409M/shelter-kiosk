from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timezone

from flask import current_app, g, session

from core.db import db_execute, db_fetchall
from core.geoip import lookup_ip
from core.helpers import utcnow_iso
from core.rate_limit import (
    get_banned_ips_snapshot,
    get_locked_keys_snapshot,
    get_rate_limit_snapshot,
)
from core.sms_sender import send_sms


ROLE_ORDER = ["admin", "shelter_director", "case_manager", "ra", "staff"]


def current_role() -> str:
    return (session.get("role") or "").strip()


def require_admin_role() -> bool:
    return current_role() == "admin"


def require_admin_or_shelter_director_role() -> bool:
    return current_role() in {"admin", "shelter_director"}


def allowed_roles_to_create():
    if require_admin_role():
        return {"admin", "shelter_director", "staff", "case_manager", "ra"}

    if current_role() == "shelter_director":
        return {"staff", "case_manager", "ra"}

    return set()


def all_roles():
    return {"admin", "shelter_director", "staff", "case_manager", "ra"}


def ordered_roles(role_set):
    return [r for r in ROLE_ORDER if r in role_set]


def scalar_value(rows, default=0):
    if not rows:
        return default

    row = rows[0]

    if isinstance(row, dict):
        return next(iter(row.values()), default)

    if isinstance(row, (list, tuple)) and row:
        return row[0]

    return default


def row_value(row, key: str, default=""):
    if isinstance(row, dict):
        return row.get(key, default)

    try:
        return row[key]
    except Exception:
        return default


def serialize_rows(rows, fields: list[str]) -> list[dict]:
    out = []

    for row in rows or []:
        item = {}
        for field in fields:
            value = row_value(row, field, "")
            item[field] = "" if value is None else value
        out.append(item)

    return out


def extract_detail_value(details: str, key: str) -> str:
    if not details:
        return ""

    prefix = f"{key}="
    for line in details.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip()

    return ""


def build_attack_intelligence(rows):
    ip_counter = Counter()
    username_counter = Counter()

    for row in rows or []:
        details = row.get("action_details", "") if isinstance(row, dict) else ""
        ip = extract_detail_value(details, "ip")
        username = extract_detail_value(details, "username")

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


def build_attack_map_points(top_attacking_ips: list[dict]) -> list[dict]:
    points = []

    for row in top_attacking_ips or []:
        ip = str(row.get("ip", "") or "").strip()
        attempts = int(row.get("attempts", 0) or 0)

        if not ip:
            continue

        geo = lookup_ip(ip)

        lat = geo.get("lat")
        lon = geo.get("lon")

        if lat is None or lon is None:
            continue

        points.append(
            {
                "ip": ip,
                "attempts": attempts,
                "lat": lat,
                "lon": lon,
                "city": geo.get("city", ""),
                "region": geo.get("region", ""),
                "country": geo.get("country", ""),
            }
        )

    return points


def build_locked_username_snapshot():
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


def _expired_timestamp(value) -> bool:
    if not value:
        return False

    raw = str(value).strip()
    if not raw:
        return False

    try:
        raw = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt <= datetime.now(timezone.utc)
    except Exception:
        return False


def load_security_settings() -> dict:
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

    updates = []

    if _expired_timestamp(row_value(row, "sms_system_expires_at", "")):
        updates.append(("sms_system_enabled", True, "sms_system_expires_at"))

    if _expired_timestamp(row_value(row, "kiosk_intake_expires_at", "")):
        updates.append(("kiosk_intake_enabled", True, "kiosk_intake_expires_at"))

    if _expired_timestamp(row_value(row, "admin_login_only_expires_at", "")):
        updates.append(("admin_login_only_mode", False, "admin_login_only_expires_at"))

    if _expired_timestamp(row_value(row, "security_alerts_expires_at", "")):
        updates.append(("security_alerts_enabled", True, "security_alerts_expires_at"))

    if updates:
        now = utcnow_iso()

        for field, value, expires_field in updates:
            db_execute(
                f"""
                UPDATE security_settings
                SET {field} = {("%s" if kind == "pg" else "?")},
                    {expires_field} = NULL,
                    updated_at = {("%s" if kind == "pg" else "?")}
                WHERE id = (SELECT id FROM security_settings ORDER BY id ASC LIMIT 1)
                """,
                (
                    value if kind == "pg" else (1 if value else 0),
                    now,
                ),
            )

        rows = db_fetchall("SELECT * FROM security_settings ORDER BY id ASC LIMIT 1")
        row = rows[0] if rows else {}

    return {
        "sms_system_enabled": bool(row_value(row, "sms_system_enabled", True)),
        "kiosk_intake_enabled": bool(row_value(row, "kiosk_intake_enabled", True)),
        "admin_login_only_mode": bool(row_value(row, "admin_login_only_mode", False)),
        "security_alerts_enabled": bool(row_value(row, "security_alerts_enabled", True)),
        "failed_login_alert_threshold": int(row_value(row, "failed_login_alert_threshold", 15) or 15),
        "attacker_ip_alert_threshold": int(row_value(row, "attacker_ip_alert_threshold", 10) or 10),
        "targeted_username_alert_threshold": int(row_value(row, "targeted_username_alert_threshold", 10) or 10),
        "lockout_seconds": int(row_value(row, "lockout_seconds", 900) or 900),
        "ip_ban_seconds": int(row_value(row, "ip_ban_seconds", 1800) or 1800),
        "alert_cooldown_seconds": int(row_value(row, "alert_cooldown_seconds", 1800) or 1800),
        "sms_system_expires_at": row_value(row, "sms_system_expires_at", ""),
        "kiosk_intake_expires_at": row_value(row, "kiosk_intake_expires_at", ""),
        "admin_login_only_expires_at": row_value(row, "admin_login_only_expires_at", ""),
        "security_alerts_expires_at": row_value(row, "security_alerts_expires_at", ""),
    }


def load_recent_security_incidents(limit: int = 10) -> list[dict]:
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
                "id": row_value(row, "id", ""),
                "incident_type": row_value(row, "incident_type", ""),
                "severity": row_value(row, "severity", ""),
                "title": row_value(row, "title", ""),
                "details": row_value(row, "details", ""),
                "related_ip": row_value(row, "related_ip", ""),
                "related_username": row_value(row, "related_username", ""),
                "status": row_value(row, "status", ""),
                "created_at": row_value(row, "created_at", ""),
            }
        )

    return incidents


def build_recent_staff_sessions(limit: int = 12) -> list[dict]:
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
        username = (row_value(row, "staff_username", "") or "").strip()
        if not username:
            details = row_value(row, "action_details", "") or ""
            username = extract_detail_value(details, "username")

        if not username or username in sessions:
            continue

        action_type = (row_value(row, "action_type", "") or "").strip()
        created_at = row_value(row, "created_at", "") or ""

        sessions[username] = {
            "username": username,
            "status": "active" if action_type == "login" else "ended",
            "last_seen": created_at,
            "last_action": action_type,
        }

    active_rows = [row for row in sessions.values() if row["status"] == "active"]
    active_rows.sort(key=lambda item: str(item.get("last_seen", "")), reverse=True)
    return active_rows[:limit]


def security_alert_cooldown_hit(key: str, window_seconds: int) -> bool:
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


def load_admin_alert_numbers() -> list[str]:
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
        phone = (row_value(row, "mobile_phone", "") or "").strip()
        if phone and phone not in numbers:
            numbers.append(phone)

    return numbers


def incident_exists_recently(
    incident_type: str,
    related_ip: str = "",
    related_username: str = "",
    window_seconds: int = 1800,
) -> bool:
    kind = g.get("db_kind")

    rows = db_fetchall(
        """
        SELECT id
        FROM security_incidents
        WHERE incident_type = %s
          AND COALESCE(related_ip, '') = %s
          AND COALESCE(related_username, '') = %s
          AND NULLIF(created_at, '')::timestamptz >= NOW() - (%s * INTERVAL '1 second')
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


def create_security_incident(
    incident_type: str,
    severity: str,
    title: str,
    details: str,
    related_ip: str = "",
    related_username: str = "",
) -> None:
    if incident_exists_recently(incident_type, related_ip, related_username):
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
        (
            incident_type,
            severity,
            title,
            details,
            related_ip or "",
            related_username or "",
            "open",
            now,
            now,
        ),
    )


def maybe_create_security_incidents(
    *,
    failed_login_count: int,
    top_attacking_ips: list[dict],
    targeted_usernames: list[dict],
    banned_ips: list[dict],
    locked_usernames: list[dict],
    settings: dict,
) -> None:
    ip_threshold = settings["attacker_ip_alert_threshold"]
    user_threshold = settings["targeted_username_alert_threshold"]
    failed_threshold = settings["failed_login_alert_threshold"]

    if banned_ips:
        row = banned_ips[0]
        create_security_incident(
            "banned_ip",
            "high",
            "Banned IP Active",
            f"An IP is currently banned for hostile activity. ip={row.get('ip', '')}",
            related_ip=row.get("ip", ""),
        )

    if locked_usernames:
        row = locked_usernames[0]
        create_security_incident(
            "locked_username",
            "high",
            "Locked Username Active",
            f"A username is currently locked due to repeated login failures. username={row.get('username', '')}",
            related_username=row.get("username", ""),
        )

    if top_attacking_ips and int(top_attacking_ips[0].get("attempts", 0)) >= ip_threshold:
        row = top_attacking_ips[0]
        create_security_incident(
            "attacker_ip_threshold",
            "high",
            "Attacker IP Threshold Reached",
            f"IP {row.get('ip', '')} reached {row.get('attempts', 0)} failed login attempts.",
            related_ip=row.get("ip", ""),
        )

    if targeted_usernames and int(targeted_usernames[0].get("attempts", 0)) >= user_threshold:
        row = targeted_usernames[0]
        create_security_incident(
            "targeted_username_threshold",
            "high",
            "Username Targeting Threshold Reached",
            f"Username {row.get('username', '')} reached {row.get('attempts', 0)} failed login attempts.",
            related_username=row.get("username", ""),
        )

    if failed_login_count >= failed_threshold:
        create_security_incident(
            "failed_logins_threshold",
            "medium",
            "Failed Login Threshold Reached",
            f"Failed logins reached {failed_login_count} in the last 24 hours.",
        )


def maybe_send_security_alerts(
    *,
    failed_login_count: int,
    top_attacking_ips: list[dict],
    targeted_usernames: list[dict],
    banned_ips: list[dict],
    locked_usernames: list[dict],
    settings: dict,
) -> None:
    if not settings["security_alerts_enabled"]:
        return

    if not settings["sms_system_enabled"]:
        return

    numbers = load_admin_alert_numbers()
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

    if security_alert_cooldown_hit(alert_key, cooldown):
        return

    for number in numbers:
        try:
            send_sms(number, alert_message, enforce_consent=False)
        except Exception:
            continue


def build_admin_dashboard_payload(*, send_alerts: bool = False) -> dict:
    is_pg = bool(current_app.config.get("DATABASE_URL"))
    settings = load_security_settings()

    total_users = scalar_value(
        db_fetchall("SELECT COUNT(*) AS c FROM staff_users")
    )

    active_users = scalar_value(
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

    failed_login_count = scalar_value(
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
    top_attacking_ips, targeted_usernames = build_attack_intelligence(failed_logins_24h)
    attack_map_points = build_attack_map_points(top_attacking_ips)

    banned_ips = get_banned_ips_snapshot()
    locked_usernames = build_locked_username_snapshot()
    rate_limit_activity = get_rate_limit_snapshot()
    recent_staff_sessions = build_recent_staff_sessions()

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

    maybe_create_security_incidents(
        failed_login_count=int(failed_login_count or 0),
        top_attacking_ips=top_attacking_ips,
        targeted_usernames=targeted_usernames,
        banned_ips=banned_ips,
        locked_usernames=locked_usernames,
        settings=settings,
    )

    recent_security_incidents = load_recent_security_incidents()

    if send_alerts:
        maybe_send_security_alerts(
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
        "attack_map_points": attack_map_points,
        "banned_ips": banned_ips,
        "locked_usernames": locked_usernames,
        "rate_limit_activity": rate_limit_activity,
        "kiosk_security_events": kiosk_security_events,
        "recent_staff_sessions": recent_staff_sessions,
        "recent_security_incidents": recent_security_incidents,
        "live_payload": {
            "settings": settings,
            "failed_login_count": int(failed_login_count or 0),
            "recent_audit": serialize_rows(recent_audit, ["created_at", "staff_username", "action_type", "action_details"]),
            "recent_failed_logins": serialize_rows(recent_failed_logins, ["created_at", "action_type", "action_details"]),
            "kiosk_security_events": serialize_rows(kiosk_security_events, ["created_at", "action_type", "action_details"]),
            "recent_staff_sessions": recent_staff_sessions,
            "recent_security_incidents": recent_security_incidents,
            "top_attacking_ips": top_attacking_ips,
            "targeted_usernames": targeted_usernames,
            "attack_map_points": attack_map_points,
            "banned_ips": banned_ips,
            "locked_usernames": locked_usernames,
            "rate_limit_activity": rate_limit_activity,
        },
    }


def audit_where_from_request(request):
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
