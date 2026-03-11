"""
Database schema bootstrap.

This module is responsible for creating all tables and performing
safe schema evolution for existing deployments.
"""

from __future__ import annotations

from flask import current_app, g

from . import schema_core
from . import schema_audit
from . import schema_residents
from . import schema_attendance
from . import schema_transport
from . import schema_rate_limit


def init_db() -> None:
    """
    Initialize database schema.

    This function is safe to run repeatedly.
    It will create missing tables and apply safe upgrades.
    """

    # Determine DB engine
    kind = g.get("db_kind")

    if not kind:
        if current_app.config.get("DATABASE_URL"):
            kind = "pg"
        else:
            kind = "sqlite"

    # -------------------------------------------------
    # 1. Base tables
    # -------------------------------------------------

    schema_core.ensure_tables(kind)

    # -------------------------------------------------
    # 2. Core schema upgrades (safe migrations)
    # -------------------------------------------------

    schema_core.ensure_columns_and_security_upgrades(kind)

    # -------------------------------------------------
    # 3. Operational tables
    # -------------------------------------------------

    schema_audit.ensure_tables(kind)
    schema_residents.ensure_tables(kind)
    schema_attendance.ensure_tables(kind)
    schema_transport.ensure_tables(kind)

    # -------------------------------------------------
    # 4. Rate limit and security telemetry
    # -------------------------------------------------

    schema_rate_limit.ensure_tables(kind)

    # -------------------------------------------------
    # 5. Bootstrap default security settings
    # -------------------------------------------------

    _ensure_default_security_settings()


def _ensure_default_security_settings() -> None:
    """
    Ensure one security_settings row exists.

    This allows the platform to have default circuit breaker
    and alert threshold settings without requiring manual inserts.
    """

    from core.db import db_fetchall, db_execute
    from core.helpers import utcnow_iso

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
        VALUES (TRUE, TRUE, FALSE, TRUE, 15, 10, 10, 900, 1800, 1800, %s, %s)
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
        VALUES (1,1,0,1,15,10,10,900,1800,1800,?,?)
        """,
        (now, now),
    )
