"""
Database schema bootstrap.

This module creates all tables and applies safe schema upgrades
for both SQLite and PostgreSQL.
"""

from __future__ import annotations

from flask import current_app, g

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso

from . import schema_audit
from . import schema_attendance
from . import schema_core
from . import schema_rate_limit
from . import schema_residents
from . import schema_transport


def init_db() -> None:
    """
    Initialize database schema.

    Safe to run repeatedly on startup.
    """
    kind = g.get("db_kind")

    if not kind:
        kind = "pg" if current_app.config.get("DATABASE_URL") else "sqlite"

    # 1. Base tables
    schema_core.ensure_tables(kind)

    # 2. Safe schema upgrades for existing deployments
    schema_core.ensure_columns_and_security_upgrades(kind)

    # 3. Operational tables
    schema_audit.ensure_tables(kind)
    schema_residents.ensure_tables(kind)
    schema_attendance.ensure_tables(kind)
    schema_transport.ensure_tables(kind)
    schema_rate_limit.ensure_tables(kind)

    # 4. Seed default security settings
    _ensure_default_security_settings()


def _ensure_default_security_settings() -> None:
    """
    Ensure one default security_settings row exists.
    """
    rows = db_fetchall("SELECT id FROM security_settings LIMIT 1")
    if rows:
        return

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
        if g.get("db_kind") == "pg"
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
            True if g.get("db_kind") == "pg" else 1,
            True if g.get("db_kind") == "pg" else 1,
            False if g.get("db_kind") == "pg" else 0,
            True if g.get("db_kind") == "pg" else 1,
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
