"""
Lightweight database migrations.

Each migration is identified by a unique name and runs once.
Safe for repeated app starts and repeated deploys.
"""

from __future__ import annotations

from flask import g

from core.db import db_execute, db_fetchone


def _ensure_migrations_table(kind: str) -> None:
    if kind == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )


def has_migration(kind: str, name: str) -> bool:
    row = db_fetchone(
        "SELECT name FROM schema_migrations WHERE name = %s"
        if kind == "pg"
        else "SELECT name FROM schema_migrations WHERE name = ?",
        (name,),
    )
    return bool(row)


def record_migration(kind: str, name: str) -> None:
    db_execute(
        "INSERT INTO schema_migrations (name) VALUES (%s)"
        if kind == "pg"
        else "INSERT INTO schema_migrations (name) VALUES (?)",
        (name,),
    )


def run_migration(kind: str, name: str, fn) -> None:
    """
    Run a migration function once.

    fn must be a no argument callable that performs the schema change.
    """
    _ensure_migrations_table(kind)

    if has_migration(kind, name):
        return

    fn()
    record_migration(kind, name)
