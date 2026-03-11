"""
Public database schema entry point.

This file is intentionally small.

It does not define every table directly. Instead, it orchestrates
focused schema modules so database logic stays maintainable and
does not grow back into one giant monolith.
"""

from __future__ import annotations

from flask import g

from . import schema_bootstrap
from . import schema_comms
from . import schema_core
from . import schema_outcomes
from . import schema_people
from . import schema_program
from . import schema_requests
from . import schema_shelters


def _ensure_default_security_settings(kind: str) -> None:
    """
    Ensure one default security_settings row exists.

    Safe to call repeatedly.
    """
    from core.db import db_execute, db_fetchall
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


def init_db() -> None:
    """
    Initialize all database tables, follow up schema adjustments,
    indexes, and bootstrap data.

    Safe to call repeatedly on app startup.
    """
    kind = g.get("db_kind")
    if not kind:
        raise RuntimeError("Database kind is not set on flask.g")

    # 1. Base tables
    schema_core.ensure_tables(kind)
    schema_shelters.ensure_tables(kind)
    schema_people.ensure_tables(kind)
    schema_program.ensure_tables(kind)
    schema_outcomes.ensure_tables(kind)
    schema_requests.ensure_tables(kind)
    schema_comms.ensure_tables(kind)

    # 2. Security schema upgrades
    schema_core.ensure_columns_and_security_upgrades(kind)
    _ensure_default_security_settings(kind)

    # 3. Follow up schema adjustments
    schema_people.ensure_columns_and_constraints(kind)
    schema_requests.ensure_columns_and_constraints(kind)

    # 4. Indexes
    schema_people.ensure_indexes()
    schema_program.ensure_indexes()
    schema_outcomes.ensure_indexes()
    schema_requests.ensure_indexes()
    schema_comms.ensure_indexes(kind)

    # 5. Seed / bootstrap tasks
    schema_bootstrap.ensure_all(kind)
