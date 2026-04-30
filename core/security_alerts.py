from __future__ import annotations

from collections import deque

from flask import current_app, g

from core.admin_dashboard_utils import row_value
from core.db import db_execute, db_fetchall
from core.sms_sender import send_sms


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
        count = int(rows[0]["c"] if isinstance(rows[0], dict) else rows[0][0]) if rows else 0
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


def maybe_send_security_alerts(
    *,
    failed_login_count: int,
    top_attacking_ips: list[dict],
    targeted_usernames: list[dict],
    banned_ips: list[dict],
    locked_usernames: list[dict],
    settings: dict,
    top_threat_score: int = 0,
    top_threats: list[dict] | None = None,
) -> None:
    if not settings["security_alerts_enabled"]:
        return

    if not settings["sms_system_enabled"]:
        return

    numbers = load_admin_alert_numbers()
    if not numbers:
        return

    cooldown = settings["alert_cooldown_seconds"]
    top_threats = top_threats or []

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
    elif top_threat_score >= 10 and top_threats:
        row = top_threats[0]
        alert_key = f"security_alert:threat_score:{row.get('ip', 'unknown')}"
        alert_message = f"DWC security alert. IP {row.get('ip', 'unknown')} reached threat score {row.get('score', 0)} with repeated hostile behavior. Review the admin dashboard immediately."
    elif (
        top_attacking_ips
        and int(top_attacking_ips[0].get("attempts", 0)) >= settings["attacker_ip_alert_threshold"]
    ):
        row = top_attacking_ips[0]
        alert_key = f"security_alert:attacker_ip:{row.get('ip', 'unknown')}"
        alert_message = f"DWC security alert. High volume hostile activity detected from IP {row.get('ip', 'unknown')} with {row.get('attempts', 0)} events in the last 24 hours."
    elif (
        targeted_usernames
        and int(targeted_usernames[0].get("attempts", 0))
        >= settings["targeted_username_alert_threshold"]
    ):
        row = targeted_usernames[0]
        alert_key = f"security_alert:targeted_user:{row.get('username', 'unknown')}"
        alert_message = f"DWC security alert. Username {row.get('username', 'unknown')} has been targeted {row.get('attempts', 0)} times in the last 24 hours."
    elif failed_login_count >= settings["failed_login_alert_threshold"]:
        alert_key = "security_alert:failed_logins_24h"
        alert_message = f"DWC security alert. Hostile security events reached {failed_login_count} in the last 24 hours. Review the admin dashboard."

    if not alert_key or not alert_message:
        return

    if security_alert_cooldown_hit(alert_key, cooldown):
        return

    for number in numbers:
        try:
            send_sms(number, alert_message, enforce_consent=False)
        except Exception:
            continue
