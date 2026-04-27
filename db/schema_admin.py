"""
Admin data quality schema.

This module stores admin review decisions for data quality findings that
require human review rather than automatic repair.
"""

from __future__ import annotations

from flask import current_app

from core.db import db_execute

from .schema_helpers import create_table, safe_add_column


def ensure_duplicate_name_reviews_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS duplicate_name_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name_key TEXT NOT NULL,
            last_name_key TEXT NOT NULL,
            status TEXT NOT NULL,
            reviewed_by_user_id INTEGER,
            reviewed_at TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS duplicate_name_reviews (
            id SERIAL PRIMARY KEY,
            first_name_key TEXT NOT NULL,
            last_name_key TEXT NOT NULL,
            status TEXT NOT NULL,
            reviewed_by_user_id INTEGER,
            reviewed_at TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )

    safe_add_column(kind, "duplicate_name_reviews", "primary_resident_id INTEGER")
    safe_add_column(kind, "duplicate_name_reviews", "primary_selected_by_user_id INTEGER")
    safe_add_column(kind, "duplicate_name_reviews", "primary_selected_at TEXT")


def ensure_resident_merge_history_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_merge_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            primary_resident_id INTEGER NOT NULL,
            merged_resident_ids TEXT NOT NULL,
            first_name_key TEXT NOT NULL,
            last_name_key TEXT NOT NULL,
            merged_by_user_id INTEGER,
            affected_tables TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_merge_history (
            id SERIAL PRIMARY KEY,
            primary_resident_id INTEGER NOT NULL,
            merged_resident_ids TEXT NOT NULL,
            first_name_key TEXT NOT NULL,
            last_name_key TEXT NOT NULL,
            merged_by_user_id INTEGER,
            affected_tables TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
    )


def ensure_system_alerts_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS system_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_key TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            source_module TEXT NOT NULL DEFAULT '',
            entity_type TEXT NOT NULL DEFAULT '',
            entity_id INTEGER,
            metadata TEXT NOT NULL DEFAULT '',
            resolved_by_user_id INTEGER,
            resolved_at TEXT,
            resolution_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS system_alerts (
            id SERIAL PRIMARY KEY,
            alert_key TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            source_module TEXT NOT NULL DEFAULT '',
            entity_type TEXT NOT NULL DEFAULT '',
            entity_id INTEGER,
            metadata TEXT NOT NULL DEFAULT '',
            resolved_by_user_id INTEGER,
            resolved_at TEXT,
            resolution_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_tables(kind: str) -> None:
    ensure_duplicate_name_reviews_table(kind)
    ensure_resident_merge_history_table(kind)
    ensure_system_alerts_table(kind)


def ensure_indexes() -> None:
    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS duplicate_name_reviews_name_status_idx
            ON duplicate_name_reviews (first_name_key, last_name_key, status)
            """
        )
    except Exception:
        current_app.logger.exception("Failed to create duplicate name review index.")

    try:
        db_execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS duplicate_name_reviews_verified_uidx
            ON duplicate_name_reviews (first_name_key, last_name_key, status)
            WHERE status = 'verified_separate_people'
            """
        )
    except Exception:
        current_app.logger.exception(
            "Failed to create duplicate name verified review unique index."
        )

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_merge_history_primary_idx
            ON resident_merge_history (primary_resident_id, created_at)
            """
        )
    except Exception:
        current_app.logger.exception("Failed to create resident merge history primary index.")

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS resident_merge_history_name_idx
            ON resident_merge_history (first_name_key, last_name_key, created_at)
            """
        )
    except Exception:
        current_app.logger.exception("Failed to create resident merge history name index.")

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS system_alerts_status_idx
            ON system_alerts (status, severity, created_at)
            """
        )
    except Exception:
        current_app.logger.exception("Failed to create system alerts index.")
