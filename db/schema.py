"""
Messaging and throttling schema objects.
"""

from __future__ import annotations

from core.db import db_execute

from .schema_helpers import create_table


def ensure_twilio_message_status_table(kind: str) -> None:
    """
    Ensure twilio_message_status table exists.
    """
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS twilio_message_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_sid TEXT NOT NULL,
            message_status TEXT NOT NULL,
            error_code TEXT,
            to_number TEXT,
            from_number TEXT,
            account_sid TEXT,
            api_version TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS twilio_message_status (
            id SERIAL PRIMARY KEY,
            message_sid TEXT NOT NULL,
            message_status TEXT NOT NULL,
            error_code TEXT,
            to_number TEXT,
            from_number TEXT,
            account_sid TEXT,
            api_version TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """,
    )


def ensure_rate_limit_events_table(kind: str) -> None:
    """
    Ensure rate_limit_events table exists on Postgres.
    """
    if kind != "pg":
        return

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limit_events (
            id SERIAL PRIMARY KEY,
            k TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )


def ensure_tables(kind: str) -> None:
    """
    Ensure all communications related tables exist.
    """
    ensure_twilio_message_status_table(kind)
    ensure_rate_limit_events_table(kind)


def ensure_indexes(kind: str) -> None:
    """
    Ensure indexes exist for communication related tables.
    """
    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS twilio_message_status_sid_idx "
            "ON twilio_message_status (message_sid)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS twilio_message_status_created_idx "
            "ON twilio_message_status (created_at)"
        )
    except Exception:
        pass

    if kind == "pg":
        db_execute(
            "CREATE INDEX IF NOT EXISTS rate_limit_events_k_idx "
            "ON rate_limit_events (k)"
        )
        db_execute(
            "CREATE INDEX IF NOT EXISTS rate_limit_events_created_at_idx "
            "ON rate_limit_events (created_at)"
        )
