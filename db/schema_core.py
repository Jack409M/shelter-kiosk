"""
Core low churn schema objects.
"""

from __future__ import annotations

from core.db import db_execute
from .schema_helpers import create_table


def ensure_staff_users_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS staff_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS staff_users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
    )


def ensure_security_settings_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS security_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sms_system_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            kiosk_intake_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            admin_login_only_mode BOOLEAN NOT NULL DEFAULT FALSE,
            security_alerts_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            failed_login_alert_threshold INTEGER NOT NULL DEFAULT 15,
            attacker_ip_alert_threshold INTEGER NOT NULL DEFAULT 10,
            targeted_username_alert_threshold INTEGER NOT NULL DEFAULT 10,
            lockout_seconds INTEGER NOT NULL DEFAULT 900,
            ip_ban_seconds INTEGER NOT NULL DEFAULT 1800,
            alert_cooldown_seconds INTEGER NOT NULL DEFAULT 1800,
            sms_system_expires_at TEXT,
            kiosk_intake_expires_at TEXT,
            admin_login_only_expires_at TEXT,
            security_alerts_expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS security_settings (
            id SERIAL PRIMARY KEY,
            sms_system_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            kiosk_intake_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            admin_login_only_mode BOOLEAN NOT NULL DEFAULT FALSE,
            security_alerts_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            failed_login_alert_threshold INTEGER NOT NULL DEFAULT 15,
            attacker_ip_alert_threshold INTEGER NOT NULL DEFAULT 10,
            targeted_username_alert_threshold INTEGER NOT NULL DEFAULT 10,
            lockout_seconds INTEGER NOT NULL DEFAULT 900,
            ip_ban_seconds INTEGER NOT NULL DEFAULT 1800,
            alert_cooldown_seconds INTEGER NOT NULL DEFAULT 1800,
            sms_system_expires_at TEXT,
            kiosk_intake_expires_at TEXT,
            admin_login_only_expires_at TEXT,
            security_alerts_expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """,
    )


def ensure_security_incidents_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS security_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            details TEXT,
            related_ip TEXT,
            related_username TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS security_incidents (
            id SERIAL PRIMARY KEY,
            incident_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            details TEXT,
            related_ip TEXT,
            related_username TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """,
    )


def ensure_columns_and_security_upgrades(kind: str) -> None:
    """
    Safe schema evolution for existing deployments.
    """

    try:
        db_execute("ALTER TABLE staff_users ADD COLUMN first_name TEXT")
    except Exception:
        pass

    try:
        db_execute("ALTER TABLE staff_users ADD COLUMN last_name TEXT")
    except Exception:
        pass

    try:
        db_execute("ALTER TABLE staff_users ADD COLUMN mobile_phone TEXT")
    except Exception:
        pass

    try:
        db_execute("ALTER TABLE security_settings ADD COLUMN sms_system_expires_at TEXT")
    except Exception:
        pass

    try:
        db_execute("ALTER TABLE security_settings ADD COLUMN kiosk_intake_expires_at TEXT")
    except Exception:
        pass

    try:
        db_execute("ALTER TABLE security_settings ADD COLUMN admin_login_only_expires_at TEXT")
    except Exception:
        pass

    try:
        db_execute("ALTER TABLE security_settings ADD COLUMN security_alerts_expires_at TEXT")
    except Exception:
        pass


def ensure_organizations_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            public_name TEXT NOT NULL,
            primary_color TEXT,
            secondary_color TEXT,
            logo_url TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            public_name TEXT NOT NULL,
            primary_color TEXT,
            secondary_color TEXT,
            logo_url TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """,
    )


def ensure_tables(kind: str) -> None:
    ensure_staff_users_table(kind)
    ensure_security_settings_table(kind)
    ensure_security_incidents_table(kind)
    ensure_organizations_table(kind)
    ensure_columns_and_security_upgrades(kind)
