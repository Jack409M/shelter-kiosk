"""
Shelter schema helpers.
"""

from __future__ import annotations

from core.db import db_execute


def ensure_tables(kind: str) -> None:
    """
    Create shelters table and seed default DWC shelters.

    Safe to call repeatedly.
    """
    sqlite_sql = """
    CREATE TABLE IF NOT EXISTS shelters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """

    pg_sql = """
    CREATE TABLE IF NOT EXISTS shelters (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """

    db_execute(pg_sql if kind == "pg" else sqlite_sql)

    _seed_default_shelters(kind)


def _seed_default_shelters(kind: str) -> None:
    """
    Ensure the default DWC shelters exist.
    """
    default_shelters = ["Abba", "Haven", "Gratitude"]

    if kind == "pg":
        for name in default_shelters:
            db_execute(
                """
                INSERT INTO shelters (name)
                VALUES (%s)
                ON CONFLICT (name) DO NOTHING
                """,
                (name,),
            )
    else:
        for name in default_shelters:
            db_execute(
                """
                INSERT OR IGNORE INTO shelters (name)
                VALUES (?)
                """,
                (name,),
            )
