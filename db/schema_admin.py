"""
Admin data quality schema.

This module stores admin review decisions for data quality findings that
require human review rather than automatic repair.
"""

from __future__ import annotations

from flask import current_app

from core.db import db_execute
from .schema_helpers import create_table


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


def ensure_tables(kind: str) -> None:
    ensure_duplicate_name_reviews_table(kind)


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
        current_app.logger.exception("Failed to create duplicate name verified review unique index.")
