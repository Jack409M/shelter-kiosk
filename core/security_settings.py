from __future__ import annotations

from flask import g

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso


def _row_value(row, key: str, default=""):
    if isinstance(row, dict):
        return row.get(key, default)

    try:
        return row[key]
    except Exception:
        return default


def _expired_timestamp(value) -> bool:
    if not value:
        return False

    raw = str(value).strip()
    if not raw:
        return False

    try:
        from datetime import UTC, datetime

        raw = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt <= datetime.now(UTC)
    except Exception:
        return False


def _bool_for_db(value: bool, kind: str):
    if kind == "pg":
        return value
    return 1 if value else 0


def ensure_security_settings_row() -> dict:
    kind = g.get("db_kind")
    rows = db_fetchall("SELECT * FROM security_settings ORDER BY id ASC LIMIT 1")
    row = rows[0] if rows else {}

    if row:
        return row

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
            _bool_for_db(True, kind),
            _bool_for_db(True, kind),
            _bool_for_db(False, kind),
            _bool_for_db(True, kind),
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
    return rows[0] if rows else {}


def _reset_expired_temporary_settings(row: dict) -> dict:
    kind = g.get("db_kind")
    updates = []

    if _expired_timestamp(_row_value(row, "sms_system_expires_at", "")):
        updates.append(("sms_system_enabled", True, "sms_system_expires_at"))

    if _expired_timestamp(_row_value(row, "kiosk_intake_expires_at", "")):
        updates.append(("kiosk_intake_enabled", True, "kiosk_intake_expires_at"))

    if _expired_timestamp(_row_value(row, "admin_login_only_expires_at", "")):
        updates.append(("admin_login_only_mode", False, "admin_login_only_expires_at"))

    if _expired_timestamp(_row_value(row, "security_alerts_expires_at", "")):
        updates.append(("security_alerts_enabled", True, "security_alerts_expires_at"))

    if not updates:
        return row

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
            (_bool_for_db(value, kind), now),
        )

    rows = db_fetchall("SELECT * FROM security_settings ORDER BY id ASC LIMIT 1")
    return rows[0] if rows else {}


def load_security_settings() -> dict:
    row = ensure_security_settings_row()
    row = _reset_expired_temporary_settings(row)

    return {
        "sms_system_enabled": bool(_row_value(row, "sms_system_enabled", True)),
        "kiosk_intake_enabled": bool(_row_value(row, "kiosk_intake_enabled", True)),
        "admin_login_only_mode": bool(_row_value(row, "admin_login_only_mode", False)),
        "security_alerts_enabled": bool(_row_value(row, "security_alerts_enabled", True)),
        "failed_login_alert_threshold": int(
            _row_value(row, "failed_login_alert_threshold", 15) or 15
        ),
        "attacker_ip_alert_threshold": int(_row_value(row, "attacker_ip_alert_threshold", 10) or 10),
        "targeted_username_alert_threshold": int(
            _row_value(row, "targeted_username_alert_threshold", 10) or 10
        ),
        "lockout_seconds": int(_row_value(row, "lockout_seconds", 900) or 900),
        "ip_ban_seconds": int(_row_value(row, "ip_ban_seconds", 1800) or 1800),
        "alert_cooldown_seconds": int(_row_value(row, "alert_cooldown_seconds", 1800) or 1800),
        "sms_system_expires_at": _row_value(row, "sms_system_expires_at", ""),
        "kiosk_intake_expires_at": _row_value(row, "kiosk_intake_expires_at", ""),
        "admin_login_only_expires_at": _row_value(row, "admin_login_only_expires_at", ""),
        "security_alerts_expires_at": _row_value(row, "security_alerts_expires_at", ""),
    }
